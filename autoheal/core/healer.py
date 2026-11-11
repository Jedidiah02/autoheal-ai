"""Multi-strategy self-healing selector engine for UI test automation."""

import re
import difflib
import time
import uuid
from typing import List, Tuple, Optional, Dict, Any
from bs4 import BeautifulSoup, Tag

from autoheal.core.models import (
    SelectorStrategy,
    SelectorMetadata,
    HealingEvent,
)


class SelfHealingEngine:
    """Intelligent selector resolver that repairs broken UI locators at runtime."""

    def __init__(self, confidence_threshold: float = 0.45):
        self.confidence_threshold = confidence_threshold
        self.healing_history: List[HealingEvent] = []

    def heal_selector(
        self,
        broken_selector: str,
        dom_html: str,
        metadata: Optional[SelectorMetadata] = None,
        test_id: str = "test-case",
        step_name: str = "ui-action"
    ) -> Tuple[Optional[str], Optional[HealingEvent]]:
        """Attempt to find a replacement selector for a broken locator using live DOM."""
        start_time = time.perf_counter()
        soup = BeautifulSoup(dom_html, "html.parser")

        # 1. Parse hints from broken selector
        inferred_tag, inferred_id, inferred_classes, inferred_text = self._parse_selector_clues(broken_selector)

        expected_tag = (metadata.target_tag if metadata else None) or inferred_tag
        expected_text = (metadata.target_text if metadata else None) or inferred_text
        expected_role = metadata.target_role if metadata else None

        # 2. Extract candidate elements from DOM
        candidates = self._find_candidate_elements(soup, expected_tag)
        if not candidates:
            # Fallback to interactive elements
            candidates = soup.find_all(["button", "a", "input", "select", "textarea", "div", "span"])

        scored_candidates: List[Tuple[Tag, float, str]] = []

        for candidate in candidates:
            score, reason = self._compute_similarity_score(
                candidate=candidate,
                broken_selector=broken_selector,
                expected_tag=expected_tag,
                expected_text=expected_text,
                expected_role=expected_role,
                inferred_id=inferred_id,
                inferred_classes=inferred_classes,
                metadata=metadata
            )
            if score >= self.confidence_threshold:
                scored_candidates.append((candidate, score, reason))

        if not scored_candidates:
            return None, None

        # Sort by confidence descending
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        best_candidate, best_score, diff_reason = scored_candidates[0]

        # Generate a robust, modern selector for the matched element
        healed_selector = self._generate_resilient_selector(best_candidate)
        duration_ms = (time.perf_counter() - start_time) * 1000

        event = HealingEvent(
            id=f"heal-{uuid.uuid4().hex[:8]}",
            test_id=test_id,
            step_name=step_name,
            original_selector=broken_selector,
            healed_selector=healed_selector,
            confidence=round(best_score, 3),
            strategy=SelectorStrategy.HEURISTIC_ATTRIBUTE,
            diff_explanation=diff_reason,
            execution_time_ms=round(duration_ms, 2)
        )

        self.healing_history.append(event)
        return healed_selector, event

    def _parse_selector_clues(self, selector: str) -> Tuple[Optional[str], Optional[str], List[str], Optional[str]]:
        """Extract tag, id, classes, and text clues from a CSS or text selector."""
        tag = None
        element_id = None
        classes = []
        text = None

        # Text matching like: text="Login" or button:has-text("Submit")
        text_match = re.search(r'text[=:]\s*["\']?([^"\']+)["\']?', selector, re.IGNORECASE)
        if text_match:
            text = text_match.group(1).strip()

        # Tag name
        tag_match = re.match(r'^([a-zA-Z0-9]+)', selector)
        if tag_match:
            tag = tag_match.group(1).lower()

        # ID: #my-id or [id="my-id"]
        id_match = re.search(r'#([a-zA-Z0-9_\-]+)|\[id=["\']?([^"\'\]]+)["\']?\]', selector)
        if id_match:
            element_id = id_match.group(1) or id_match.group(2)

        # Classes: .btn-primary
        class_matches = re.findall(r'\.([a-zA-Z0-9_\-]+)', selector)
        if class_matches:
            classes = class_matches

        return tag, element_id, classes, text

    def _find_candidate_elements(self, soup: BeautifulSoup, tag: Optional[str]) -> List[Tag]:
        """Find pool of candidate elements matching tag or interactive tags."""
        if tag and tag not in ["div", "span"]:
            elements = soup.find_all(tag)
            if elements:
                return elements
        return soup.find_all(["button", "a", "input", "select", "textarea", "form", "div", "span"])

    def _compute_similarity_score(
        self,
        candidate: Tag,
        broken_selector: str,
        expected_tag: Optional[str],
        expected_text: Optional[str],
        expected_role: Optional[str],
        inferred_id: Optional[str],
        inferred_classes: List[str],
        metadata: Optional[SelectorMetadata]
    ) -> Tuple[float, str]:
        """Weighted scoring based on tag, text, aria, testid, id and classes."""
        score = 0.0
        reasons = []

        # 1. Tag Match (weight: 0.15)
        candidate_tag = candidate.name.lower()
        if expected_tag and candidate_tag == expected_tag.lower():
            score += 0.15
            reasons.append(f"Matching tag <{candidate_tag}>")
        elif expected_tag in ["button", "a"] and candidate_tag in ["button", "a", "input"]:
            score += 0.08
            reasons.append("Compatible interactive tag")

        # 2. Text / Value / Label / Placeholder Content Match (weight: 0.40)
        candidate_text = candidate.get_text(strip=True)
        candidate_val = candidate.get("value", "")
        candidate_placeholder = candidate.get("placeholder", "")
        
        # Check neighboring label text for inputs
        label_text = ""
        if candidate.name == "input":
            # Direct previous sibling label
            prev_label = candidate.find_previous_sibling("label")
            if prev_label:
                label_text = prev_label.get_text(strip=True)
            elif candidate.parent and candidate.parent.name in ["div", "form", "p", "section"]:
                parent_label = candidate.parent.find("label")
                if parent_label:
                    label_text = parent_label.get_text(strip=True)

        combined_text = f"{candidate_text} {candidate_val} {candidate_placeholder} {label_text}".strip()

        target_text = expected_text
        if target_text and combined_text:
            ratio = difflib.SequenceMatcher(None, target_text.lower(), combined_text.lower()).ratio()
            if target_text.lower() in combined_text.lower():
                score += 0.40
                reasons.append(f"Text/Label match '{target_text}' (found: '{combined_text}')")
            elif ratio > 0.5:
                score += 0.35 * ratio
                reasons.append(f"Fuzzy text match ({ratio:.2f}) with '{target_text}'")

        # 3. Accessibility & Identifiers: data-testid, aria-label, name, type (weight: 0.30)
        candidate_attrs = candidate.attrs
        aria_label = candidate_attrs.get("aria-label", "")
        data_testid = candidate_attrs.get("data-testid") or candidate_attrs.get("data-test", "")
        name_attr = candidate_attrs.get("name", "")
        role_attr = candidate_attrs.get("role", "")
        type_attr = candidate_attrs.get("type", "")

        if expected_role and role_attr.lower() == expected_role.lower():
            score += 0.15
            reasons.append(f"Role match '{role_attr}'")

        if metadata and metadata.expected_attributes:
            for k, expected_v in metadata.expected_attributes.items():
                if candidate_attrs.get(k) == expected_v:
                    score += 0.30
                    reasons.append(f"Attribute match {k}='{expected_v}'")

        if target_text and aria_label and target_text.lower() in aria_label.lower():
            score += 0.35
            reasons.append(f"aria-label '{aria_label}' matches '{target_text}'")

        # Check if inferred ID relates to name or type
        if inferred_id:
            cleaned_inferred = re.sub(r'[^a-zA-Z]', '', inferred_id.lower())
            if name_attr and (cleaned_inferred in name_attr.lower() or name_attr.lower() in cleaned_inferred):
                score += 0.25
                reasons.append(f"name attribute '{name_attr}' matches clue '{inferred_id}'")
            if type_attr and type_attr.lower() in cleaned_inferred:
                score += 0.20
                reasons.append(f"type='{type_attr}' matches clue '{inferred_id}'")

        # 4. ID Substring / Token Match (weight: 0.15)
        candidate_id = candidate_attrs.get("id", "")
        if inferred_id and candidate_id:
            if inferred_id.lower() == candidate_id.lower():
                score += 0.25
                reasons.append(f"Exact ID match #{candidate_id}")
            else:
                id_ratio = difflib.SequenceMatcher(None, inferred_id.lower(), candidate_id.lower()).ratio()
                if id_ratio > 0.5:
                    score += 0.15 * id_ratio
                    reasons.append(f"Partial ID similarity ({id_ratio:.2f}) between #{inferred_id} and #{candidate_id}")

        # 5. Class Overlap (weight: 0.10)
        candidate_classes = candidate.get("class", [])
        if isinstance(candidate_classes, list) and inferred_classes:
            overlap = set(inferred_classes).intersection(set(candidate_classes))
            if overlap:
                ratio = len(overlap) / max(len(inferred_classes), len(candidate_classes))
                score += 0.10 * ratio
                reasons.append(f"Shared CSS classes: {list(overlap)}")

        reason_str = "; ".join(reasons) if reasons else "Generic structural match"
        return min(score, 1.0), reason_str

    def _generate_resilient_selector(self, element: Tag) -> str:
        """Construct a resilient, prioritized selector for the matched DOM element."""
        tag = element.name

        # Priority 1: data-testid or data-test
        if "data-testid" in element.attrs:
            return f"{tag}[data-testid='{element['data-testid']}']"
        if "data-test" in element.attrs:
            return f"{tag}[data-test='{element['data-test']}']"

        # Priority 2: Semantic ID (if not random looking)
        elem_id = element.get("id")
        if elem_id and not re.search(r'[0-9a-f]{8,}', elem_id):
            return f"#{elem_id}"

        # Priority 3: aria-label
        aria_label = element.get("aria-label")
        if aria_label:
            return f"{tag}[aria-label='{aria_label}']"

        # Priority 4: name attribute (for form inputs)
        name = element.get("name")
        if name:
            return f"{tag}[name='{name}']"

        # Priority 5: Text content for buttons/links
        text = element.get_text(strip=True)
        if text and tag in ["button", "a"]:
            cleaned_text = re.sub(r'\s+', ' ', text)[:30]
            return f"{tag}:has-text('{cleaned_text}')"

        # Priority 6: Meaningful classes
        classes = element.get("class", [])
        if classes:
            valid_classes = [c for c in classes if not re.match(r'^(css-|jsx-|tw-|_)', c)]
            if valid_classes:
                return f"{tag}.{valid_classes[0]}"

        # Fallback to tag + type or generic
        elem_type = element.get("type")
        if elem_type:
            return f"{tag}[type='{elem_type}']"

        return tag
