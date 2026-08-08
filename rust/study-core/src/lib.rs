//! LecturePack Study Core — deterministic mastery and review-state logic.
//!
//! This is the single native component in the Study overhaul. It owns only
//! deterministic state transitions (mastery, review timing, weak-area
//! ranking, quick-study session building, and study summaries). It never
//! touches AI, prompts, content generation, or the filesystem — Python owns
//! those. Every function is pure and returns structured JSON so no panic can
//! cross the Python boundary.

use chrono::{DateTime, Duration, Utc};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Four simple user-facing mastery states. Students never see spaced-repetition
/// terminology; these are the only labels the UI needs.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum MasteryState {
    New,
    Learning,
    Mastered,
    NeedsReview,
}

impl MasteryState {
    fn as_str(self) -> &'static str {
        match self {
            MasteryState::New => "NEW",
            MasteryState::Learning => "LEARNING",
            MasteryState::Mastered => "MASTERED",
            MasteryState::NeedsReview => "NEEDS_REVIEW",
        }
    }
}

/// Conservative review intervals in days. A student never configures these.
const REVIEW_INTERVALS_DAYS: [i64; 4] = [1, 3, 7, 14];

/// Per-concept progress tracked by the Rust core.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConceptProgress {
    pub concept_id: String,
    pub attempts: u32,
    pub correct: u32,
    pub incorrect: u32,
    pub last_reviewed: Option<String>,
    pub next_review: Option<String>,
    pub mastery: MasteryState,
}

impl ConceptProgress {
    fn new(concept_id: &str) -> Self {
        Self {
            concept_id: concept_id.to_string(),
            attempts: 0,
            correct: 0,
            incorrect: 0,
            last_reviewed: None,
            next_review: None,
            mastery: MasteryState::New,
        }
    }
}

/// A validated source reference. Python validates segment/slide IDs before
/// persisting; Rust only reasons about the already-validated structure.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SourceRef {
    pub segment_id: Option<String>,
    pub start_ms: Option<u64>,
    pub end_ms: Option<u64>,
    pub slide_id: Option<String>,
    pub preview: Option<String>,
}

/// A study concept with its source grounding.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Concept {
    pub id: String,
    pub title: String,
    pub explanation: String,
    pub sources: Vec<SourceRef>,
    pub emphasis: Option<String>,
}

/// A flashcard mapped to at least one concept.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Flashcard {
    pub id: String,
    pub front: String,
    pub back: String,
    pub concept_ids: Vec<String>,
    pub sources: Vec<SourceRef>,
}

/// A quiz question mapped to at least one concept.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuizQuestion {
    pub id: String,
    pub question: String,
    pub qtype: String,
    pub options: Vec<String>,
    pub correct_index: Option<usize>,
    pub explanation: Option<String>,
    pub concept_ids: Vec<String>,
    pub sources: Vec<SourceRef>,
}

/// The full Study V2 content model (static generated material).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StudyContent {
    pub schema_version: u32,
    pub concepts: Vec<Concept>,
    pub flashcards: Vec<Flashcard>,
    pub quiz: Vec<QuizQuestion>,
}

/// The full Study V2 progress model (user-specific mutable state).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StudyProgress {
    pub schema_version: u32,
    pub concepts: HashMap<String, ConceptProgress>,
    pub flashcard_results: HashMap<String, FlashcardResult>,
    pub quiz_attempts: Vec<QuizAttempt>,
    pub quick_study: Option<QuickStudyState>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FlashcardResult {
    pub card_id: String,
    pub correct: bool,
    pub reviewed_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuizAttempt {
    pub question_id: String,
    pub correct: bool,
    pub answered_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuickStudyState {
    pub started_at: String,
    pub items: Vec<QuickStudyItem>,
    pub index: usize,
    pub correct: u32,
    pub total: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuickStudyItem {
    pub kind: String, // "concept" | "flashcard" | "quiz"
    pub id: String,
    pub concept_id: String,
}

/// A single review result from the UI.
#[derive(Debug, Clone, Deserialize)]
pub struct ReviewResult {
    pub concept_id: String,
    pub correct: bool,
    pub reviewed_at: Option<String>,
}

/// A flashcard review result.
#[derive(Debug, Clone, Deserialize)]
pub struct FlashcardReview {
    pub card_id: String,
    pub concept_ids: Vec<String>,
    pub correct: bool,
    pub reviewed_at: Option<String>,
}

/// A quiz answer result.
#[derive(Debug, Clone, Deserialize)]
pub struct QuizReview {
    pub question_id: String,
    pub concept_ids: Vec<String>,
    pub correct: bool,
    pub answered_at: Option<String>,
}

fn now_iso() -> String {
    Utc::now().to_rfc3339()
}

fn parse_iso(value: &str) -> Option<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(value).ok().map(|dt| dt.with_timezone(&Utc))
}

/// Apply one review result to a concept's progress and return the updated
/// progress. This is the single source of truth for mastery transitions.
fn apply_review(progress: &mut ConceptProgress, correct: bool, reviewed_at: &str) {
    progress.attempts += 1;
    if correct {
        progress.correct += 1;
    } else {
        progress.incorrect += 1;
    }
    progress.last_reviewed = Some(reviewed_at.to_string());

    // Any meaningful miss drops the concept to NEEDS_REVIEW.
    if !correct {
        progress.mastery = MasteryState::NeedsReview;
        progress.next_review = None;
        return;
    }

    // Successful review progression:
    //   NEW        -> LEARNING
    //   LEARNING   -> MASTERED
    //   NEEDS_REVIEW -> LEARNING
    //   MASTERED   -> stays MASTERED (spaced review only)
    let next = match progress.mastery {
        MasteryState::New => MasteryState::Learning,
        MasteryState::Learning => MasteryState::Mastered,
        MasteryState::NeedsReview => MasteryState::Learning,
        MasteryState::Mastered => MasteryState::Mastered,
    };
    progress.mastery = next;

    // Schedule the next review at a conservative interval based on how many
    // successful reviews this concept has accumulated.
    let interval_days = REVIEW_INTERVALS_DAYS
        .get(progress.correct.saturating_sub(1) as usize)
        .copied()
        .unwrap_or(*REVIEW_INTERVALS_DAYS.last().unwrap());
    if let Some(now) = parse_iso(reviewed_at) {
        let next = now + Duration::days(interval_days);
        progress.next_review = Some(next.to_rfc3339());
    }
}

/// Calculate the mastery state for a concept given its attempt history.
/// This is a pure helper used by tests and diagnostics.
#[pyfunction]
fn calculate_mastery(attempts: u32, correct: u32, incorrect: u32) -> String {
    if incorrect > 0 {
        return MasteryState::NeedsReview.as_str().to_string();
    }
    if attempts == 0 {
        return MasteryState::New.as_str().to_string();
    }
    if correct >= 2 {
        return MasteryState::Mastered.as_str().to_string();
    }
    MasteryState::Learning.as_str().to_string()
}

/// Record a flashcard review result and update the associated concepts.
#[pyfunction]
fn record_flashcard_result(
    progress_json: &str,
    review_json: &str,
) -> PyResult<String> {
    let mut progress: StudyProgress = serde_json::from_str(progress_json)
        .map_err(|e| PyValueError::new_err(format!("invalid progress: {e}")))?;
    let review: FlashcardReview = serde_json::from_str(review_json)
        .map_err(|e| PyValueError::new_err(format!("invalid review: {e}")))?;

    let reviewed_at = review.reviewed_at.clone().unwrap_or_else(now_iso);
    progress.flashcard_results.insert(
        review.card_id.clone(),
        FlashcardResult {
            card_id: review.card_id,
            correct: review.correct,
            reviewed_at: reviewed_at.clone(),
        },
    );

    for concept_id in &review.concept_ids {
        let entry = progress
            .concepts
            .entry(concept_id.clone())
            .or_insert_with(|| ConceptProgress::new(concept_id));
        apply_review(entry, review.correct, &reviewed_at);
    }

    serde_json::to_string(&progress)
        .map_err(|e| PyValueError::new_err(format!("serialize failed: {e}")))
}

/// Record a quiz answer result and update the associated concepts.
#[pyfunction]
fn record_quiz_result(
    progress_json: &str,
    review_json: &str,
) -> PyResult<String> {
    let mut progress: StudyProgress = serde_json::from_str(progress_json)
        .map_err(|e| PyValueError::new_err(format!("invalid progress: {e}")))?;
    let review: QuizReview = serde_json::from_str(review_json)
        .map_err(|e| PyValueError::new_err(format!("invalid review: {e}")))?;

    let answered_at = review.answered_at.clone().unwrap_or_else(now_iso);
    progress.quiz_attempts.push(QuizAttempt {
        question_id: review.question_id,
        correct: review.correct,
        answered_at: answered_at.clone(),
    });

    for concept_id in &review.concept_ids {
        let entry = progress
            .concepts
            .entry(concept_id.clone())
            .or_insert_with(|| ConceptProgress::new(concept_id));
        apply_review(entry, review.correct, &answered_at);
    }

    serde_json::to_string(&progress)
        .map_err(|e| PyValueError::new_err(format!("serialize failed: {e}")))
}

/// Rank concepts for review. Returns a list of concept IDs in priority order:
/// 1. Needs Review
/// 2. Due Learning concepts
/// 3. New important concepts
/// 4. Recently weak concepts
/// 5. Mastered concepts only when appropriate for spaced review
#[pyfunction]
fn rank_review_concepts(
    progress_json: &str,
    content_json: &str,
    now: Option<String>,
) -> PyResult<String> {
    let progress: StudyProgress = serde_json::from_str(progress_json)
        .map_err(|e| PyValueError::new_err(format!("invalid progress: {e}")))?;
    let content: StudyContent = serde_json::from_str(content_json)
        .map_err(|e| PyValueError::new_err(format!("invalid content: {e}")))?;

    let now = now.unwrap_or_else(now_iso);
    let now_dt = parse_iso(&now).unwrap_or_else(Utc::now);

    // Build a map of concept id -> emphasis (for importance ranking).
    let emphasis: HashMap<&str, &str> = content
        .concepts
        .iter()
        .filter_map(|c| c.emphasis.as_deref().map(|e| (c.id.as_str(), e)))
        .collect();

    let mut needs_review: Vec<&str> = Vec::new();
    let mut due_learning: Vec<&str> = Vec::new();
    let mut new_important: Vec<&str> = Vec::new();
    let mut weak: Vec<&str> = Vec::new();
    let mut mastered_due: Vec<&str> = Vec::new();

    for concept in &content.concepts {
        let id = concept.id.as_str();
        let entry = progress.concepts.get(id);
        match entry {
            Some(p) => match p.mastery {
                MasteryState::NeedsReview => needs_review.push(id),
                MasteryState::Learning => {
                    let due = p.next_review.as_deref().and_then(parse_iso)
                        .map(|dt| dt <= now_dt)
                        .unwrap_or(true);
                    if due {
                        due_learning.push(id);
                    }
                }
                MasteryState::Mastered => {
                    let due = p.next_review.as_deref().and_then(parse_iso)
                        .map(|dt| dt <= now_dt)
                        .unwrap_or(false);
                    if due {
                        mastered_due.push(id);
                    }
                }
                MasteryState::New => {
                    if emphasis.contains_key(id) {
                        new_important.push(id);
                    }
                }
            },
            None => {
                if emphasis.contains_key(id) {
                    new_important.push(id);
                }
            }
        }
    }

    // Weak concepts: those with a high miss ratio but not yet NeedsReview.
    for (id, p) in &progress.concepts {
        if p.attempts > 0 && p.incorrect > 0 && p.mastery != MasteryState::NeedsReview {
            weak.push(id.as_str());
        }
    }

    let mut ranked: Vec<&str> = Vec::new();
    ranked.extend(needs_review);
    ranked.extend(due_learning);
    ranked.extend(new_important);
    ranked.extend(weak);
    ranked.extend(mastered_due);

    serde_json::to_string(&ranked)
        .map_err(|e| PyValueError::new_err(format!("serialize failed: {e}")))
}

/// Build a Quick Study session from content + progress. Returns a prioritized
/// list of items (concept refreshers, flashcards, quiz questions).
#[pyfunction]
fn build_quick_study_session(
    progress_json: &str,
    content_json: &str,
    now: Option<String>,
) -> PyResult<String> {
    let progress: StudyProgress = serde_json::from_str(progress_json)
        .map_err(|e| PyValueError::new_err(format!("invalid progress: {e}")))?;
    let content: StudyContent = serde_json::from_str(content_json)
        .map_err(|e| PyValueError::new_err(format!("invalid content: {e}")))?;

    let ranked = rank_review_concepts(progress_json, content_json, now)?;
    let ranked_ids: Vec<String> = serde_json::from_str(&ranked)
        .map_err(|e| PyValueError::new_err(format!("rank failed: {e}")))?;

    let mut items: Vec<QuickStudyItem> = Vec::new();

    // 1. Concept refreshers for the top-ranked concepts (up to 2).
    for id in ranked_ids.iter().take(2) {
        items.push(QuickStudyItem {
            kind: "concept".to_string(),
            id: id.clone(),
            concept_id: id.clone(),
        });
    }

    // 2. Flashcards mapped to the ranked concepts (up to 5).
    let mut flash_count = 0;
    for card in &content.flashcards {
        if flash_count >= 5 {
            break;
        }
        if card.concept_ids.iter().any(|cid| ranked_ids.contains(cid)) {
            items.push(QuickStudyItem {
                kind: "flashcard".to_string(),
                id: card.id.clone(),
                concept_id: card.concept_ids.first().cloned().unwrap_or_default(),
            });
            flash_count += 1;
        }
    }

    // 3. Quiz questions mapped to the ranked concepts (up to 3).
    let mut quiz_count = 0;
    for q in &content.quiz {
        if quiz_count >= 3 {
            break;
        }
        if q.concept_ids.iter().any(|cid| ranked_ids.contains(cid)) {
            items.push(QuickStudyItem {
                kind: "quiz".to_string(),
                id: q.id.clone(),
                concept_id: q.concept_ids.first().cloned().unwrap_or_default(),
            });
            quiz_count += 1;
        }
    }

    // If nothing was ranked (all new, no emphasis), fall back to the first
    // few concepts/flashcards/quiz questions so Quick Study is never empty.
    if items.is_empty() {
        for concept in content.concepts.iter().take(2) {
            items.push(QuickStudyItem {
                kind: "concept".to_string(),
                id: concept.id.clone(),
                concept_id: concept.id.clone(),
            });
        }
        for card in content.flashcards.iter().take(5) {
            items.push(QuickStudyItem {
                kind: "flashcard".to_string(),
                id: card.id.clone(),
                concept_id: card.concept_ids.first().cloned().unwrap_or_default(),
            });
        }
        for q in content.quiz.iter().take(3) {
            items.push(QuickStudyItem {
                kind: "quiz".to_string(),
                id: q.id.clone(),
                concept_id: q.concept_ids.first().cloned().unwrap_or_default(),
            });
        }
    }

    let state = QuickStudyState {
        started_at: now_iso(),
        items,
        index: 0,
        correct: 0,
        total: 0,
    };

    serde_json::to_string(&state)
        .map_err(|e| PyValueError::new_err(format!("serialize failed: {e}")))
}

/// Calculate a study summary: counts per mastery state, cards completed,
/// quiz best score, and overall progress percent.
#[pyfunction]
fn calculate_study_summary(
    progress_json: &str,
    content_json: &str,
) -> PyResult<String> {
    let progress: StudyProgress = serde_json::from_str(progress_json)
        .map_err(|e| PyValueError::new_err(format!("invalid progress: {e}")))?;
    let content: StudyContent = serde_json::from_str(content_json)
        .map_err(|e| PyValueError::new_err(format!("invalid content: {e}")))?;
    let _ = &progress;

    let mut mastered = 0u32;
    let mut learning = 0u32;
    let mut needs_review = 0u32;
    let mut new_count = 0u32;

    for concept in &content.concepts {
        match progress.concepts.get(&concept.id).map(|p| p.mastery) {
            Some(MasteryState::Mastered) => mastered += 1,
            Some(MasteryState::Learning) => learning += 1,
            Some(MasteryState::NeedsReview) => needs_review += 1,
            _ => new_count += 1,
        }
    }

    let total_concepts = content.concepts.len() as u32;
    let progress_pct = if total_concepts == 0 {
        0.0
    } else {
        ((mastered + learning) as f64 / total_concepts as f64 * 100.0).round()
    };

    let cards_completed = progress.flashcard_results.len() as u32;
    let quiz_best = progress
        .quiz_attempts
        .iter()
        .filter(|a| a.correct)
        .count() as u32;

    let summary = serde_json::json!({
        "mastered": mastered,
        "learning": learning,
        "needs_review": needs_review,
        "new": new_count,
        "total_concepts": total_concepts,
        "progress_percent": progress_pct,
        "cards_completed": cards_completed,
        "quiz_correct": quiz_best,
        "quiz_attempts": progress.quiz_attempts.len() as u32,
    });

    serde_json::to_string(&summary)
        .map_err(|e| PyValueError::new_err(format!("serialize failed: {e}")))
}

/// Diagnostic/version function for tests and packaging verification.
#[pyfunction]
fn study_core_info() -> String {
    serde_json::json!({
        "available": true,
        "implementation": "rust",
        "version": "0.1.0",
    })
    .to_string()
}

/// Python module definition.
#[pymodule]
fn lecturepack_study_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(calculate_mastery, m)?)?;
    m.add_function(wrap_pyfunction!(record_flashcard_result, m)?)?;
    m.add_function(wrap_pyfunction!(record_quiz_result, m)?)?;
    m.add_function(wrap_pyfunction!(rank_review_concepts, m)?)?;
    m.add_function(wrap_pyfunction!(build_quick_study_session, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_study_summary, m)?)?;
    m.add_function(wrap_pyfunction!(study_core_info, m)?)?;
    Ok(())
}

// --------------------------------------------------------------------------- //
// Unit tests
// --------------------------------------------------------------------------- //
#[cfg(test)]
mod tests {
    use super::*;

    fn empty_progress() -> StudyProgress {
        StudyProgress {
            schema_version: 2,
            concepts: HashMap::new(),
            flashcard_results: HashMap::new(),
            quiz_attempts: Vec::new(),
            quick_study: None,
        }
    }

    fn sample_content() -> StudyContent {
        StudyContent {
            schema_version: 2,
            concepts: vec![
                Concept {
                    id: "c1".into(),
                    title: "Discovery of Troy".into(),
                    explanation: "Schliemann claimed Hisarlik was Troy.".into(),
                    sources: vec![SourceRef {
                        segment_id: Some("s1".into()),
                        start_ms: Some(1122000),
                        end_ms: Some(1150000),
                        slide_id: Some("slide-14".into()),
                        preview: None,
                    }],
                    emphasis: Some("emphasized".into()),
                },
                Concept {
                    id: "c2".into(),
                    title: "Legacy".into(),
                    explanation: "His methods influenced archaeology.".into(),
                    sources: vec![],
                    emphasis: None,
                },
            ],
            flashcards: vec![
                Flashcard {
                    id: "f1".into(),
                    front: "What was Schliemann trying to prove?".into(),
                    back: "That Hisarlik was Troy.".into(),
                    concept_ids: vec!["c1".into()],
                    sources: vec![],
                },
                Flashcard {
                    id: "f2".into(),
                    front: "What is legacy?".into(),
                    back: "Influence on archaeology.".into(),
                    concept_ids: vec!["c2".into()],
                    sources: vec![],
                },
            ],
            quiz: vec![
                QuizQuestion {
                    id: "q1".into(),
                    question: "Where did Schliemann dig?".into(),
                    qtype: "multiple_choice".into(),
                    options: vec!["Hisarlik".into(), "Athens".into()],
                    correct_index: Some(0),
                    explanation: Some("He claimed Hisarlik was Troy.".into()),
                    concept_ids: vec!["c1".into()],
                    sources: vec![],
                },
            ],
        }
    }

    #[test]
    fn new_concept_starts_new() {
        let p = ConceptProgress::new("c1");
        assert_eq!(p.mastery, MasteryState::New);
        assert_eq!(p.attempts, 0);
    }

    #[test]
    fn one_success_moves_new_to_learning() {
        let mut p = ConceptProgress::new("c1");
        apply_review(&mut p, true, &now_iso());
        assert_eq!(p.mastery, MasteryState::Learning);
        assert_eq!(p.correct, 1);
        assert!(p.next_review.is_some());
    }

    #[test]
    fn two_successes_move_to_mastered() {
        let mut p = ConceptProgress::new("c1");
        apply_review(&mut p, true, &now_iso());
        apply_review(&mut p, true, &now_iso());
        assert_eq!(p.mastery, MasteryState::Mastered);
    }

    #[test]
    fn miss_sets_needs_review() {
        let mut p = ConceptProgress::new("c1");
        apply_review(&mut p, true, &now_iso());
        apply_review(&mut p, false, &now_iso());
        assert_eq!(p.mastery, MasteryState::NeedsReview);
        assert_eq!(p.incorrect, 1);
    }

    #[test]
    fn needs_review_success_returns_to_learning() {
        let mut p = ConceptProgress::new("c1");
        apply_review(&mut p, false, &now_iso());
        assert_eq!(p.mastery, MasteryState::NeedsReview);
        apply_review(&mut p, true, &now_iso());
        assert_eq!(p.mastery, MasteryState::Learning);
    }

    #[test]
    fn mastered_stays_mastered_on_success() {
        let mut p = ConceptProgress::new("c1");
        apply_review(&mut p, true, &now_iso());
        apply_review(&mut p, true, &now_iso());
        apply_review(&mut p, true, &now_iso());
        assert_eq!(p.mastery, MasteryState::Mastered);
    }

    #[test]
    fn review_intervals_increase() {
        let mut p = ConceptProgress::new("c1");
        apply_review(&mut p, true, "2026-01-01T00:00:00Z");
        let first = p.next_review.clone().unwrap();
        apply_review(&mut p, true, "2026-01-02T00:00:00Z");
        let second = p.next_review.clone().unwrap();
        let d1 = parse_iso(&first).unwrap();
        let d2 = parse_iso(&second).unwrap();
        assert!(d2 > d1);
    }

    #[test]
    fn rank_prioritizes_needs_review() {
        let mut progress = empty_progress();
        let mut p = ConceptProgress::new("c1");
        apply_review(&mut p, false, &now_iso());
        progress.concepts.insert("c1".into(), p);
        let content = sample_content();
        let ranked: Vec<String> = serde_json::from_str(
            &rank_review_concepts(
                &serde_json::to_string(&progress).unwrap(),
                &serde_json::to_string(&content).unwrap(),
                None,
            ).unwrap(),
        ).unwrap();
        assert_eq!(ranked[0], "c1");
    }

    #[test]
    fn quick_study_prioritizes_weak() {
        let mut progress = empty_progress();
        let mut p = ConceptProgress::new("c1");
        apply_review(&mut p, false, &now_iso());
        progress.concepts.insert("c1".into(), p);
        let content = sample_content();
        let session: QuickStudyState = serde_json::from_str(
            &build_quick_study_session(
                &serde_json::to_string(&progress).unwrap(),
                &serde_json::to_string(&content).unwrap(),
                None,
            ).unwrap(),
        ).unwrap();
        assert!(!session.items.is_empty());
        assert_eq!(session.items[0].concept_id, "c1");
    }

    #[test]
    fn summary_counts_mastery() {
        let mut progress = empty_progress();
        let mut p = ConceptProgress::new("c1");
        apply_review(&mut p, true, &now_iso());
        apply_review(&mut p, true, &now_iso());
        progress.concepts.insert("c1".into(), p);
        let content = sample_content();
        let summary: serde_json::Value = serde_json::from_str(
            &calculate_study_summary(
                &serde_json::to_string(&progress).unwrap(),
                &serde_json::to_string(&content).unwrap(),
            ).unwrap(),
        ).unwrap();
        assert_eq!(summary["mastered"], 1);
        assert_eq!(summary["needs_review"], 0);
        assert_eq!(summary["total_concepts"], 2);
    }

    #[test]
    fn study_core_info_reports_rust() {
        let info: serde_json::Value = serde_json::from_str(&study_core_info()).unwrap();
        assert_eq!(info["available"], true);
        assert_eq!(info["implementation"], "rust");
        assert_eq!(info["version"], "0.1.0");
    }
}