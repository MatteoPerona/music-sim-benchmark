# v0 Spec — AOTY Matrix Factorization + Fan-Type Discovery

*The smallest experiment that tests the core hypothesis of the fan-reaction model, using only AOTY numeric scores. No text, no affect labeling, no encoders, no rollout. Target: 1–2 days of work, a clear go/no-go.*

---

## 1. What this tests

* **H1 (low-rank reaction structure):** fans' album scores are well explained by a low-dimensional latent model `score ≈ u_f · v_a + biases`. → measured by held-out rating prediction beating bias-only baselines.
* **H2 (interpretable fan types):** clustering the learned fan vectors `u_f` yields a small number of stable, interpretable "schools of thought." → measured by cluster stability + a readable per-cluster album profile.

If H1 fails, the whole modeling approach is in doubt before you spend anything on NLP. If H1 passes and H2 is interpretable, the skeleton of Layer 1 + a scalar Layer 3 is proven.

---

## 2. Data

**Source:** AOTY user reviews (existing `collect_aoty.py`).

**Slice — one connected scene so users co-rate (start with UK rap, reusing Feng):**

* Seed ~15–40 albums across ~10–25 artists in the same scene (users must overlap or types can't form).
* Collect all user reviews (score + username + date + text) for those albums. Text is stored but  **not used in v0** .

**Filters (apply in order):**

1. Drop reviews without a numeric score.
2. Keep only users with **≥ 3 reviews** in the slice (raise to 5 if the matrix is dense enough).
3. Keep only albums with **≥ 20 reviews** after the user filter.
4. Deduplicate (same user+album → keep latest; audit for edited/re-dated reviews — your known contamination risk).

**Resulting object:** a sparse **user × album** matrix `S` of 0–100 scores. Expect ~1–5k users × ~20–40 albums, a few thousand to ~20k observed cells. Record density (%) — below ~1% density, tighten the slice.

---

## 3. Model

Predict each observed score:

```
ŝ_{f,a} = μ + b_f + b_a + u_f · v_a
```

* `μ` global mean score (constant), `b_f` fan bias, `b_a` album bias, `u_f, v_a ∈ ℝ^d`.
* **Loss:** MSE on observed cells + L2 regularization:
  `L = Σ_{(f,a)∈obs} (s_{f,a} − ŝ_{f,a})² + λ(‖u_f‖² + ‖v_a‖² + b_f² + b_a²)`
* **Optimizer:** Adam, lr 5e-3, ~200–500 epochs (full-batch or large minibatches), early-stop on val RMSE.

**Hyperparameter sweep:**

* `d ∈ {2, 4, 8}` (the dimension of the reaction space).
* `λ ∈ {0.01, 0.1, 1.0}`.
* Pick by validation RMSE.

*(Fast smoke-test alternative before writing the loop: mean-center `S`, run `TruncatedSVD`/`NMF`, and eyeball whether users separate. Then do the proper regularized MF for real numbers.)*

---

## 4. Train / validation split

* **Primary:** randomly hold out **20% of observed ratings** (cells), train on 80%. Ensure every retained user/album still appears in train (the §2 filters make this safe). This tests reaction prediction.
* Report on the 20% held-out cells only.
* **Optional second split (stretch):** hold out whole users to probe generalization to unseen fans — expect worse numbers; documents the cold-start gap that the encoder later fixes.

---

## 5. Baselines & results table (fill this in)

| Model                          | d  | Val RMSE | Val MAE |
| ------------------------------ | -- | -------- | ------- |
| Global mean (`μ`)           | — |          |         |
| Album-mean (`μ + b_a`)      | — |          |         |
| User-mean (`μ + b_f`)       | — |          |         |
| Bias-only (`μ + b_f + b_a`) | — |          |         |
| **MF**                   | 2  |          |         |
| **MF**                   | 4  |          |         |
| **MF**                   | 8  |          |         |

The bias-only row is the one to beat — it captures "harsh users" and "loved albums" without any latent structure. MF earning a clear RMSE reduction over it is the H1 pass signal.

---

## 6. Fan-type discovery (H2)

1. Take the best MF model's fan vectors `U ∈ ℝ^{N_fans × d}`.
2. Fit a **GMM** (or k-means) for `K ∈ {3, 4, 5, 6}`; pick K by BIC + interpretability.
3. **Interpret each cluster** via its  *album score profile* : mean predicted (or observed) score per album for the cluster's members → which albums it rates high vs. low. Name the school of thought (e.g. "rates underground high, crossover low").
4. **Stability check:** retrain MF with 5 random seeds, cluster each, compute mean pairwise **Adjusted Rand Index** between the fan-assignment sets. (Clusters are more stable than raw axes because the bilinear model is rotation-invariant — this is why we interpret clusters, not dimensions.)

---

## 7. Success criteria

* **H1:** best MF test RMSE is **meaningfully below the bias-only baseline** (aim for a clear, consistent gap, not noise-level).
* **H2:** at least one K gives clusters that are (a) **stable** (mean ARI across seeds ≳ 0.5) and (b) **interpretable** — the per-cluster album profiles tell a coherent story a human recognizes.
* Bonus sanity anchor: known-signal users (e.g. accounts that only rate the underground catalog highly) land in the expected cluster.

If both hold, greenlight v1: swap the scalar score for a VAD vector from the review text (affect pipeline enters), and add the content features / encoder.

---

## 8. Explicitly out of scope for v0

Review text & VAD affect · content/fan encoders · cold-start handling · dates/rollout dynamics · artist-mix & artist-type layers · MRP calibration · cross-platform anything · nonparametric (HDP) K. All are v1+ extensions gated on the H1/H2 pass.

---

## 9. Minimal implementation sketch

```python
import pandas as pd, numpy as np, torch
from sklearn.mixture import GaussianMixture

# --- data: df with columns [user, album, score] after §2 filters ---
uids = {u:i for i,u in enumerate(df.user.unique())}
aids = {a:i for i,a in enumerate(df.album.unique())}
f = torch.tensor(df.user.map(uids).values)
a = torch.tensor(df.album.map(aids).values)
s = torch.tensor(df.score.values, dtype=torch.float)
# 80/20 split on rows
mask = torch.rand(len(s)) < 0.8

d, lam = 8, 0.1
U = torch.zeros(len(uids), d, requires_grad=True)
V = torch.zeros(len(aids), d, requires_grad=True)
bf = torch.zeros(len(uids), requires_grad=True)
ba = torch.zeros(len(aids), requires_grad=True)
mu = s[mask].mean()
opt = torch.optim.Adam([U, V, bf, ba], lr=5e-3)

for epoch in range(400):
    pred = mu + bf[f] + ba[a] + (U[f]*V[a]).sum(1)
    err  = ((pred - s)[mask]**2).mean()
    reg  = lam*(U.pow(2).mean()+V.pow(2).mean()+bf.pow(2).mean()+ba.pow(2).mean())
    loss = err + reg
    opt.zero_grad(); loss.backward(); opt.step()

# val RMSE
val_rmse = ((pred - s)[~mask]**2).mean().sqrt().item()

# fan types
gmm = GaussianMixture(n_components=5, covariance_type='full').fit(U.detach().numpy())
labels = gmm.predict(U.detach().numpy())
```

**Deliverables:** the filled §5 table; a 2D PCA/UMAP plot of `U` colored by cluster; a per-cluster album-profile table; and a one-paragraph read of whether H1/H2 passed.

---

## 10. v0.5 — Semantics enter (two steps, one change at a time)

v0 is content-blind and can't handle unseen stimuli. v0.5 fixes both, in order. Do **Step A** and **Step B** as separate diffs so you can attribute any change in accuracy.

### Step A — Turn each review into a VAD reaction target

Replace the scalar 0–100 score with a **3-D affect vector** `r = (valence, arousal, dominance)`; magnitude = intensity. Extraction pipeline (all off-the-shelf, no LLM at inference):

1. **Lexicon layer:** NRC-VAD (per-word V/A/D, coverage-weighted mean over the review) + **VADER** rules for negation, intensifiers, caps, emoji.
2. **Classifier layer:** CardiffNLP `twitter-roberta-base-emotion` (multilabel); map its emotion distribution → VAD by  **probability-weighted NRC-VAD coordinate lookup** .
3. **Intensity:** optional regressor trained on WASSA **EmoInt** for the magnitude signal.
4. **Combine** the labeling functions with a **Snorkel** label model; LF disagreement → a per-review confidence.
5. **Music-slang override LF:** a small hand-built hype lexicon ("goes hard / ate / slaps" → high V; flag "cooked" as ambiguous → human review). General lexicons get these wrong.

**Free built-in validation (do this first):** the derived  **valence should correlate with the AOTY 0–100 score** . If `corr(valence, score)` is high (aim ≳ 0.5), your affect extraction is sane; if not, fix extraction before modeling. This is a validation check v0 didn't have.

**Gold set:** ~200–500 dev + ~500–1000 test annotated with **Best-Worst Scaling** on Prolific; report **Krippendorff's α** (target ≳ 0.67). Trust valence most; arousal/dominance are noisier (r ≈ 0.5–0.6).

**Model change:** keep shared `u_f, v_a`, add a  **linear readout to 3 outputs** : `r̂_{f,a} = μ + b_f + b_a + W·(u_f ⊙ v_a)` with `W ∈ ℝ^{3×d}` (or three dim-specific bias terms sharing one interaction). Loss = MSE over the 3 dims, **weighting valence higher** than A/D. Re-run the §6 clustering on the new `U` — H2 should still hold with the richer target.

### Step B — Content encoder replaces the free album embedding (unlocks cold-start)

Instead of `v_a` being a free lookup row, make it a  **function of the album's content features** :

```
v_a = g(x_a),   x_a = [ text-embed (~384) · audio/MIR (~20) · type one-hot · deviation-from-baseline · context ]
g = small MLP → ℝ^d
```

This is the step that lets a **never-seen album/post get a vector from features alone** — the actual product capability. (Keep the fan side as free embeddings for now; change one side at a time.)

**The evaluation that matters here — held-out  *albums* , not just held-out ratings.** Add the whole-album split from §4:

| Model                              | held-out ratings RMSE | **held-out albums RMSE** |
| ---------------------------------- | --------------------- | ------------------------------ |
| Pure CF (v0)                       |                       | *can't predict — no `v`*  |
| CF + VAD target (Step A)           |                       | *can't predict*              |
| **Content encoder (Step B)** |                       |                                |

On held-out  *ratings* , the content encoder may tie or slightly trail pure CF (features are a bottleneck). On held-out *albums* it wins by default — CF literally can't play. Beating a global/genre-mean baseline on unseen albums is the  **cold-start pass signal** , i.e. proof the model can forecast reaction to new content.

### v0.5 success criteria

* `corr(derived valence, AOTY score)` ≳ 0.5 (affect extraction is trustworthy).
* Clusters from the VAD-target model remain **stable + interpretable** (H2 survives the richer target).
* Content-encoder model **generalizes to held-out albums** meaningfully better than a mean baseline (cold-start path works).

### Still out of scope after v0.5

Rollout/temporal dynamics · the artist-mix & artist-type layers · the amortized fan encoder over history · MRP calibration · cross-platform data. These are v1+ and gated on v0.5 passing.
