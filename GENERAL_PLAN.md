# Feng Sentiment Benchmark: Project Plan

## Objective

Build a benchmark that tests whether our simulation can predict how different fan segments reacted to Feng's Weekend Rockstar — using only data available before the album dropped (Feb 13, 2026). Social media sentiment is the primary signal.

---

## 1. Temporal Split

Everything hinges on a clean before/after division.

**Cutoff date: February 13, 2026** (Weekend Rockstar release)

### Training window (sim sees this)

| Period               | What happened                                                                                                                                          | Data available                                                                                                                   |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| Aug 2024 – Feb 2025 | Early singles (Friends, Devil Horns, M.I.A., Damn Phone, etc.)                                                                                         | YouTube comments + views, early Reddit/TikTok discussion, Last.fm scrobbles                                                      |
| Feb 14, 2025         | What the Feng drops                                                                                                                                    | AOTY reviews (user score 72, ~1,439 reviews), Reddit threads, YouTube reaction videos, press reviews (Pitchfork, Fader, Complex) |
| Mar – Sep 2025      | Rise to prominence. Pitchfork "Party With Feng." Complex "Best Teenage Rappers." Fader "Best albums 2025 so far"                                       | Press coverage full text, growing social following, fan page creation                                                            |
| Oct – Dec 2025      | Post-WTF singles (Princess, XOXO, When I Met You, Teenage Dreamer). XOXO and Princess get TikTok moments. Guardian article on UK underground explosion | Single-level reception data (comments, view counts, save/skip signals). These singles show the sonic direction moving toward pop |
| Late 2025            | **CTI controversy breaks** — Feng dropped his manager with no compensation after Capitol deal. Protectmaxx defense.                             | TikTok "Why did Feng get cancelled" threads, CTI's X post, Reddit backlash threads                                               |
| Jan 2026             | Cali Crazy drops (divisive — "spiritually Israeli" meme, bedroom pop pivot). J*b drops. Dazed interview. Rolling Loud announcement                    | Cali Crazy reception (strong negative signal from OG fans), J*b reception, pre-album hype/skepticism ratio                       |
| Feb 1-12, 2026       | Final pre-release period. Firework video teased. Album tracklist revealed                                                                              | Pre-release anticipation threads, pre-order signals                                                                              |

### Test window (ground truth — sim does NOT see this)

| Period              | What happened          | Data to validate against                                                                                                                                                                                              |
| ------------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Feb 13, 2026 onward | Weekend Rockstar drops | AOTY user reviews (score 49, ~946 reviews), Reddit reaction threads, YouTube reaction videos + comments, TikTok reactions, NME review (3/5), press reviews, Spotify streaming data, Substack "What Happened to Feng?" |

---

## 2. Data Collection Plan

### 2A. Reddit

**Where to look:**

- Feng's own subreddit: **r/fengeveryday**
- r/ukrap, r/ukhiphopheads, r/hiphopheads
- Search across all of Reddit for "Feng" + "rapper" OR "Weekend Rockstar" OR "What the Feng"

**What to collect per post/comment:**

- Text body
- Score (upvotes - downvotes)
- Timestamp (critical for temporal split)
- Author (for tracking repeat users across pre/post)
- Parent post (to preserve thread context)
- Subreddit (to distinguish community type)

**Access method:**

- old.reddit.com HTML scraper (no official API credentials)
- Parses listing pages and comment threads with BeautifulSoup
- Backup fetch via curl_cffi if Reddit returns 403 to plain requests
- Limitation: Reddit caps pagination at ~1,000 most recent posts per listing endpoint. Supplement with global search.

**Estimated volume:** 200-800 posts/comments mentioning Feng across all subreddits. Possibly more if the subreddit is active.

**Cost:** $0 (free API for research use)

**Time:** 3-4 hours to write scraper + run collection

### 2B. YouTube

**What to collect:**

*Video-level data:*

- All videos on @fengfengfengg channel
- Video title, description, upload date, view count, like count, comment count
- Reaction videos (search "Feng Weekend Rockstar reaction", "Feng album review")

*Comment-level data:*

- Top 200-500 comments per music video
- Comment text, like count, timestamp, author
- Reply threads (for debates between fans)

**Access method:**

- YouTube Data API v3 (free, 10,000 units/day)
- `commentThreads.list` = 1 unit per call (returns 20-100 comments per call)
- `search.list` = 1 unit per call but capped at 100 calls/day
- `videos.list` = 1 unit per call (for view counts)

**Estimated volume:** 15-25 music videos × 200-500 comments each = 3,000-12,500 comments. Plus reaction videos.

**Budget math:** At ~1 unit per commentThreads call returning 100 comments, collecting 10K comments = ~100 API calls = 100 units. Well within the 10K daily limit.

**Cost:** $0

**Time:** 2-3 hours to write scraper + run collection

### 2C. TikTok

**What to collect:**

- Comments on Feng's own posts (@fengeveryday, 28.2K followers)
- Comments on fan page posts (@fengenthusiast1 and others)
- Comments on "Why did Feng get cancelled" and "spiritually Israeli" discovery pages
- Video engagement metrics (views, likes, shares)

**Access method:**

- Apify TikTok Comments Scraper: $0.30-$5.00 per 1,000 comments depending on scraper
- Free tier: $5/month credits = 1,000-16,000 comments depending on scraper chosen
- Alternative: manual screenshot collection for small volumes

**Estimated volume:** 2,000-5,000 comments across Feng's posts + fan pages + controversy threads

**Cost:** $0-$15 (likely within Apify free tier)

**Time:** 2-3 hours (more fragile than Reddit/YouTube — may need troubleshooting)

### 2D. Album of the Year Reviews

**What to collect:**

- All user reviews for What the Feng (~1,439 reviews) with text, rating (0-100), date, username
- All user reviews for Weekend Rockstar (~946 reviews) with same fields
- Critic review scores and source names

**Access method:**

- Web scraping (no API). AOTY is server-rendered HTML, so standard requests + BeautifulSoup should work
- Pagination: reviews are paginated, typically 25 per page
- May need to handle rate limiting / anti-bot measures

**Estimated volume:** ~2,385 reviews with text + rating + date

**Cost:** $0

**Time:** 2-3 hours to write scraper + run collection. AOTY is the single richest source because every review has a numerical rating AND text AND a timestamp.

### 2E. Press Reviews (Full Text)

**What to collect:**

| Source       | Article                                                        | Method                            |
| ------------ | -------------------------------------------------------------- | --------------------------------- |
| NME          | Weekend Rockstar review (3/5)                                  | press collector                   |
| Pitchfork    | "Party With Feng" (Sep 2025), album announcement, WR review    | press collector                   |
| The Fader    | "9 key moments" (Jun 2025), "Artists to watch 2026" (Dec 2025) | press collector                   |
| Dazed        | "New Year, New Feng" (Jan 2026)                                | press collector                   |
| State Hornet | Weekend Rockstar review                                        | press collector                   |
| Complex      | "13 Best Teenage Rappers" (Aug 2025)                           | press collector                   |
| The Guardian | UK underground explosion (Dec 2025)                            | press collector                   |
| Substack     | "What Happened to Feng?" (Feb 2026)                            | press collector                   |

**Cost:** $0

**Time:** 1-2 hours

### 2F. Twitter/X

**What to collect:**

- @Fengeveryday mentions and replies
- CTI's posts about the controversy
- Fan reactions in quote tweets

**Access method:**

- X Free API: extremely limited (1,500 tweets/month read, 1 app, no search endpoint)
- X Basic ($100/month): 10,000 tweets/month read, search endpoint
- Alternative: Apify X scraper, or manual collection for key threads

**Estimated volume:** 500-2,000 relevant tweets/replies

**Cost:** $0-$100 depending on approach

**Time:** 2-3 hours

**Priority:** LOWEST among social platforms. Reddit and AOTY give better signal-to-noise. Twitter is a nice-to-have.

### Budget Summary

| Source          | Cost              | Time           | Priority        | Volume                 |
| --------------- | ----------------- | -------------- | --------------- | ---------------------- |
| AOTY reviews    | $0                | 3h             | 🔴 Critical     | ~2,400 reviews         |
| Reddit          | $0                | 4h             | 🔴 Critical     | 200-800 posts          |
| YouTube         | $0                | 3h             | 🔴 Critical     | 3K-12K comments        |
| Press           | $0                | 2h             | 🟡 High         | ~10 articles           |
| TikTok          | $0-15             | 3h             | 🟡 High         | 2K-5K comments         |
| Twitter/X       | $0-100            | 3h             | 🟢 Nice-to-have | 500-2K tweets          |
| **Total** | **$0-$115** | **~18h** |                 | **8K-22K items** |

---

## 3. Segment Classification

Before benchmarking the sim, we need to classify real users into segments so we can measure per-segment prediction accuracy. This is applied to the test window data.

### Segment Definitions

| Segment                        | Definition                                                                                                | Classification signals                                                                                                                                                 |
| ------------------------------ | --------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Underground OG**       | Followed Feng before Weekend Rockstar. Values authenticity, experimental production, underground identity | Reviewed What the Feng on AOTY (check username overlap). References WTF tracks. Uses language like "sold out," "underground," "used to be." Active in r/ukrap pre-2026 |
| **New/Casual**           | Discovered Feng via TikTok or Weekend Rockstar-era singles. Primarily pop listeners                       | Only reviewed Weekend Rockstar (no WTF review). No Reddit history pre-2026. References "vibes," pop comparisons. Found via TikTok                                      |
| **Betrayed/Moral**       | Fan sentiment driven primarily by CTI controversy or Israel controversy, not the music                    | Review/comment explicitly mentions CTI, manager, betrayal, Israel, cancelled. Score ≤ 30 with non-musical reasoning                                                   |
| **Critic/Tastemaker**    | Music-literate reviewers evaluating on craft                                                              | RYM power users (many reviews). References production technique, comparisons to other artists, discusses songwriting quality. Press reviewers                          |
| **International/Casual** | Non-UK listeners with lower context                                                                       | Non-English comments. No subreddit activity. References only the biggest singles                                                                                       |

### Classification Method

**Two-pass approach:**

1. **Rule-based first pass:**

   - AOTY: user reviewed WTF → OG candidate. User only reviewed WR → New candidate
   - Reddit: account active in r/ukrap before 2026 → OG. Account created 2026 → New
   - Content keywords: "CTI" / "manager" / "scammed" → Betrayed. "production" / "beats" / references to other artists → Critic
2. **LLM classification second pass:**

   - For ambiguous cases, feed the review text to an LLM with the segment definitions and ask it to classify
   - This is cheap (short text, Haiku-tier model) and handles nuance the rules miss
   - Validate on a 50-review hand-labeled sample before running on full dataset

**Expected distribution (hypothesis):**

- Underground OG: 25-35%
- New/Casual: 20-30%
- Betrayed/Moral: 10-20%
- Critic/Tastemaker: 10-15%
- International/Casual: 5-15%

---

## 4. Prediction Targets

The simulation sees only training window data. It must produce these predictions, which we validate against test window data.

### 4A. Aggregate Predictions

| #  | Prediction target                                       | Ground truth source                                                                                              | Metric                             |
| -- | ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| A1 | Overall sentiment ratio (% positive / mixed / negative) | AOTY review distribution + Reddit/YouTube sentiment labels                                                       | Mean absolute error on each bucket |
| A2 | AOTY user score prediction                              | Actual: 49/100                                                                                                   | Absolute error (points)            |
| A3 | Critic-fan divergence direction                         | AOTY critic 59 vs user 49 → fans harsher than critics                                                           | Binary: correct/incorrect          |
| A4 | Top 3 criticism themes                                  | Actual: (1) weak lyrics, (2) boring/sleepy production vs WTF, (3) inauthenticity/nostalgia bait                  | Theme overlap (Jaccard similarity) |
| A5 | Top 3 praise themes                                     | Actual: (1) sonic vision/ambition, (2) specific tracks (Best Friend, XOXO), (3) production quality on highlights | Theme overlap                      |

### 4B. Per-Segment Predictions

| #  | Prediction target                              | Ground truth                        | Metric                             |
| -- | ---------------------------------------------- | ----------------------------------- | ---------------------------------- |
| S1 | Underground OG sentiment distribution          | OG-classified AOTY/Reddit reviews   | MAE on pos/mix/neg buckets         |
| S2 | New/Casual sentiment distribution              | New-classified reviews              | MAE on pos/mix/neg buckets         |
| S3 | OG-specific criticism themes                   | OG reviews text                     | Theme overlap                      |
| S4 | New-fan-specific praise themes                 | New reviews text                    | Theme overlap                      |
| S5 | Betrayed segment size estimate                 | % of reviews classified as Betrayed | Absolute error (percentage points) |
| S6 | Whether OGs rate the album lower than new fans | Compare mean ratings by segment     | Binary: correct/incorrect          |

### 4C. Track-Level Predictions

| #  | Prediction target                                                       | Ground truth                                                                  | Metric                    |
| -- | ----------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------- |
| T1 | Rank-order tracks by predicted reception                                | Frequency of positive mentions per track in AOTY/Reddit + Spotify play counts | Spearman rank correlation |
| T2 | Predict which track is the "save" (fan favorite despite album backlash) | Most-mentioned positive track in reviews                                      | Top-1 accuracy            |
| T3 | Predict which track gets worst reception                                | Most-mentioned negative track                                                 | Top-1 accuracy            |
| T4 | Pre-released singles rated higher than new tracks (yes/no)              | Compare mean sentiment for XOXO/Princess vs new cuts                          | Binary: correct/incorrect |

### 4D. Controversy Impact Prediction

| #  | Prediction target                                                      | Ground truth                                                      | Metric                             |
| -- | ---------------------------------------------------------------------- | ----------------------------------------------------------------- | ---------------------------------- |
| C1 | % of negative reviews that reference non-musical factors (CTI, Israel) | Manual or LLM-coded label on negative reviews                     | Absolute error (percentage points) |
| C2 | Whether controversy independently depresses the album score            | Compare musically-focused negative reviews vs controversy-focused | Qualitative assessment             |

---

## 5. Evaluation Pipeline

### Step 1: Collect and store raw data

- All data goes into a structured format (JSON or SQLite)
- Schema per item: `{source, text, score (if applicable), timestamp, author_id, url, segment_label (initially null)}`

### Step 2: Apply temporal split

- Tag every item as `training` (before Feb 13, 2026) or `test` (Feb 13, 2026 and after)
- Verify no leakage: no test items visible to the sim

### Step 3: Classify test items into segments

- Run the two-pass classification (rule-based → LLM refinement)
- Hand-label 50 items to validate classifier accuracy
- Target: >80% agreement with hand labels

### Step 4: Compute ground truth metrics

- Aggregate: sentiment distribution, mean score, top themes (via topic modeling or LLM extraction)
- Per-segment: same metrics filtered by segment label
- Track-level: mention frequency, sentiment per track
- Controversy: % of negative reviews with non-musical content

### Step 5: Run the simulation

- Feed only training-window data to the sim
- Sim produces predictions for all targets in Section 4
- Run 3x with different random seeds / LLM models (Claude, GPT-4, Gemini) for ensemble

### Step 6: Score predictions

- Compare sim outputs to ground truth using the metrics in Section 4
- Report per-target accuracy
- Report ensemble vs individual model accuracy
- Report per-segment accuracy (where does the sim do well/poorly?)

### Step 7: Ablation studies

- **No grounding data**: Run sim with only demographic prompts (no real fan text). Compare to grounded version → measures value of real data
- **No deliberation**: Run sim with single persona per segment vs 5-10 persona debate → measures value of deliberation step
- **No controversy data**: Remove CTI controversy from training data. See if sim still predicts the backlash → measures whether musical factors alone are sufficient
- **Single model vs ensemble**: Compare individual LLM predictions to averaged ensemble → measures ensemble value

---

## 6. Sentiment Analysis Method

For labeling social media text as positive / mixed / negative (and extracting themes), use a two-tier approach:

### Tier 1: LLM-as-judge (primary)

Use Claude Haiku (cheapest, fastest) to classify each review/comment:

```
Given this review of Feng's album "Weekend Rockstar", classify:
1. Sentiment: positive / mixed / negative
2. Primary theme (1-2 words): e.g., "weak lyrics", "good production", "CTI betrayal"
3. Specific tracks mentioned (if any)
4. Is this primarily about the music or about non-musical factors (controversy, personality)?

Review: "{text}"
```

**Cost estimate:** ~$0.25 per 1,000 reviews on Haiku. For 10K items ≈ $2.50 total.

**Why LLM over VADER/BERT:** Music fan reviews are full of sarcasm, slang, irony, and context-dependent meaning ("this shit slaps" = positive, "this is mid" = negative, "the production is fire but the bars are nonexistent" = mixed). LLMs handle this far better than lexicon-based tools. Traditional NLP sentiment tools fail on domain-specific language.

### Tier 2: Validation sample

Hand-label 100 items across platforms. Compute agreement with LLM labels. Target: Cohen's kappa > 0.75. If below, refine the prompt or add few-shot examples.

---

## 7. Theme Extraction

Beyond sentiment polarity, we need to extract what people are actually talking about. This is crucial for benchmark targets A4, A5, S3, S4.

### Method

1. **LLM-extract themes** from each review (done in sentiment classification pass above)
2. **Cluster themes** using embedding similarity:
   - Embed each extracted theme string (e.g., "boring production", "sleepy beats", "lack of energy") using a small embedding model
   - Cluster with HDBSCAN or k-means
   - Label each cluster (e.g., "Production quality decline")
3. **Rank clusters** by frequency within each segment
4. **Compare** sim-predicted themes to actual theme clusters using Jaccard similarity on top-5 themes

### Expected theme clusters (hypothesis based on research so far)

**Negative themes:**

1. Lyrical weakness / surface-level / lazy writing
2. Boring / sleepy / low-energy production (vs WTF)
3. Inauthenticity / nostalgia bait / calculated aesthetics
4. CTI controversy / character issues / "sold out"
5. Tone-deaf moments (Palestine line, gender comments)
6. Israel controversy / political backlash

**Positive themes:**

1. Sonic vision / ambition / genre-blending
2. Specific standout tracks (Best Friend, XOXO, Firework)
3. Self-produced / independent / DIY credibility
4. Feel-good energy / positivity
5. Production quality on highlights

---

## 8. Timeline

### Week 1: Data Collection

| Day | Task                                                                                       | Output                                |
| --- | ------------------------------------------------------------------------------------------ | ------------------------------------- |
| 1   | Set up project repo, dependencies (PRAW, YouTube API client, BeautifulSoup, Apify account) | Dev environment ready                 |
| 1-2 | Build AOTY scraper. Collect all WTF + WR reviews                                           | ~2,400 reviews in JSON                |
| 2-3 | Build Reddit collector (PRAW). Search Feng subreddit + r/ukrap + cross-reddit search       | 200-800 posts/comments in JSON        |
| 3-4 | Build YouTube collector. Get all video metadata + top comments per video                   | Video stats + 3K-12K comments in JSON |
| 4-5 | TikTok collection via Apify. Target Feng's posts, fan pages, controversy threads           | 2K-5K comments in JSON                |
| 5   | Fetch all press review articles. Store full text                                           | ~10 articles in JSON                  |
| 5   | Find Feng's subreddit name (browse Reddit directly)                                        | r/fengeveryday                        |

### Week 2: Labeling & Ground Truth

| Day  | Task                                                                                                           | Output                                    |
| ---- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| 6    | Apply temporal split tags to all data                                                                          | Each item tagged `training` or `test` |
| 6-7  | Run LLM sentiment + theme classification on all test-window items                                              | Labeled dataset                           |
| 7    | Hand-label 100-item validation sample. Compute kappa                                                           | Validated classification quality          |
| 7-8  | Run segment classification (rule-based + LLM) on test items                                                    | Each test item assigned a segment         |
| 8    | Hand-label 50-item segment validation sample                                                                   | Validated segment accuracy                |
| 8-9  | Compute all ground truth metrics (aggregate scores, per-segment distributions, theme clusters, track mentions) | Ground truth document                     |
| 9-10 | Build the training-data package: curated, temporally-clean data the sim will ingest                            | Sim input bundle                          |

### Week 3: Simulation & Evaluation

| Day   | Task                                                                                                   | Output            |
| ----- | ------------------------------------------------------------------------------------------------------ | ----------------- |
| 11-12 | Build simulation pipeline: persona grounding from training data, segment definition, deliberation step | Working sim       |
| 12-13 | Run simulation (3 LLMs × 3 seeds = 9 runs). Produce predictions for all targets                       | Prediction matrix |
| 13-14 | Score predictions against ground truth. Compute all metrics from Section 4                             | Results table     |
| 14-15 | Run ablation studies (no grounding, no deliberation, no controversy, single model)                     | Ablation results  |

### Week 4: Package for Demo

| Day   | Task                                                                                                                              | Output                                                         |
| ----- | --------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| 16-17 | Build results dashboard / deck showing: "Here's what the sim predicted. Here's what actually happened."                           | Demo-ready materials                                           |
| 17-18 | Add forward-looking simulation: "What would happen if Feng went back to underground sound?" and "What if he doubles down on pop?" | Forward predictions (not validatable, but shows product value) |
| 18-19 | Polish, edge cases, talking points for Capitol meeting                                                                            | Final demo                                                     |
| 19-20 | Buffer / iterate                                                                                                                  | —                                                             |

**Total: ~4 weeks from start to demo-ready.**

---

## 9. Success Criteria

What would make this benchmark convincing for the Capitol meeting?

| Level                    | What it means                                                                                                                                                                         | Specific threshold                                                   |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| **Minimum viable** | Sim predicts the correct direction of reception (negative lean) and identifies at least 2 of the top 3 criticism themes                                                               | Sentiment direction correct + ≥2/3 theme overlap                    |
| **Good**           | Sim predicts the AOTY score within ±10 points, correctly predicts OGs rate it lower than new fans, identifies ≥3/5 themes, correctly predicts the controversy amplification effect  | Score within ±10 + segment ordering correct + theme overlap ≥ 0.6  |
| **Impressive**     | All of the above plus: correct track-level favorite (Best Friend or XOXO), correct prediction that pre-released singles outperform new tracks, ensemble outperforms individual models | All above + track-level accuracy + ensemble improvement demonstrated |

Even "minimum viable" is enough for the demo — the point is to show that the sim produces directionally correct, specific, actionable intelligence that the data team can't currently get from Chartmetric or Luminate.

---

## 10. Risks & Mitigations

| Risk                                                                   | Likelihood | Impact                                                 | Mitigation                                                                                                            |
| ---------------------------------------------------------------------- | ---------- | ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| **Feng's subreddit is too small** (<50 posts)                    | Medium     | Reduces Reddit ground truth quality                    | Supplement with r/ukrap mentions. Reddit may be secondary to AOTY anyway                                              |
| **AOTY anti-bot blocks scraping**                                | Medium     | Lose the richest data source                           | Use rotating proxies or Scraper API ($29/mo). Fallback: manual export of top reviews                                  |
| **Temporal contamination in training data**                      | Low        | Sim accidentally sees post-release data                | Strict timestamp filtering. Manual spot-check of training set                                                         |
| **Segment classification accuracy too low**                      | Medium     | Per-segment benchmarks become unreliable               | Accept wider confidence intervals. Report accuracy on hand-labeled validation set                                     |
| **LLM sentiment labels disagree with each other**                | Medium     | Unstable ground truth                                  | Use majority vote across 2 LLMs. Report inter-annotator agreement                                                     |
| **Sim performs well on aggregate but poorly per-segment**        | High       | Benchmark looks less impressive                        | This is actually informative — shows where more grounding data is needed. Report honestly                            |
| **Not enough pre-release negative signal for sim to pick up on** | Low        | Sim can't predict backlash without early warning signs | The Cali Crazy reception + CTI controversy ARE early warning signs. The training data includes clear negative signals |

---

## 11. What This Proves to Capitol

If the benchmark succeeds at minimum-viable level or above:

1. **"We can tell you how underground fans will react before you commit budget"** — validated by retrodicting the Weekend Rockstar backlash from pre-release signals
2. **"We can decompose your audience into segments with distinct reactions"** — shown by different sentiment distributions across OG / New / Betrayed segments
3. **"We can tell you which creative direction to invest in"** — the forward simulation (underground return vs pop doubling-down) is the product pitch. The retrodiction benchmark is why they should trust it
4. **"This is something Chartmetric and your internal data team cannot do"** — Chartmetric measures what happened. We predict what will happen and why, at the segment level
5. **"Real fan data makes it better"** — if the B2B2C flywheel ablation shows improvement from adding human signal, it directly justifies the fan prediction game as a data source, not just an engagement play
