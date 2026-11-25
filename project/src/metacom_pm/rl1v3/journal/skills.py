"""Source-bound, unapproved nonclinical method candidates from TIP35.

RAW and Method views share paragraph provenance. No professional approval or
clinical efficacy is inferred from publication, source labels, or this compiler.
"""
from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path

VERSION = "pmrl1-j-rs-skills-candidate-v1"
SOURCES = {
    "ch3": ("TIP35_ch3_sites.html", "NBK571068", "4ac626852f88220f66fa95e12c32d0da3d3e10ff2b794535b4419eef9ca53cf5"),
    "ch6": ("TIP35_ch6_sites.html", "NBK571066", "f2ee19ac9a3f1d884ba7354c56d5edb5b1cb352d44021306f041f8cf3ee430ed"),
}

# Exact paragraph selectors bind only author narrative, not linked exhibits or
# republished quotations. Selectors are stable for the pinned downloaded HTML.
DEFINITIONS = [
    dict(key="both_sides", title="Acknowledge both stated concerns", chapter="ch3",
         section="ch3.s5.4.2", starts=["Double-sided refections."],
         objective="Help the user hear both sides of their own stated tension without choosing for them.",
         conditions=["The user has explicitly described two competing wishes or concerns.", "The user wants that tension explored now."],
         moves=["Reflect both stated sides accurately and tentatively, joined without dismissing either.", "Use the user's own priorities; leave the decision with them."],
         steps=["Identify only the two concerns actually stated.", "Offer a balanced paraphrase; invite correction if uncertain."],
         stops=["The user declines exploration or asks for only one side to be addressed."],
         prohibited=["Inventing an unstated concern", "Turning the reflection into pressure to change"]),
    dict(key="reflection", title="Reflect meaning without adding facts", chapter="ch3",
         section="ch3.s4.3.2", starts=["Simple reflections are fairly straightforward.", "Be open to being wrong."],
         objective="Show understanding of the user's stated experience with a tentative, accurate paraphrase.",
         conditions=["A current feeling or concern is visible.", "The user has not prohibited emotional paraphrase."],
         moves=["Paraphrase what is present; make uncertain interpretations tentative.", "Accept correction and revise the interpretation."],
         steps=["Separate explicit facts from guesses.", "Reflect the concern concisely without explaining it as a diagnosis."],
         stops=["The user asks for a factual or practical answer without paraphrase."],
         prohibited=["Claiming to know unspoken feelings", "Diagnosis or certainty about motives"]),
    dict(key="autonomy", title="Respect the user's choice", chapter="ch3",
         section="ch3.s5.4.2", starts=["Emphasis on personal autonomy."],
         objective="Support voluntary choice without dismissing the user or taking control.",
         conditions=["A choice or boundary belongs to the user."],
         moves=["Acknowledge the user's right to choose.", "Offer bounded help if requested while leaving final choice with them."],
         steps=["Recognize the stated boundary.", "Avoid coercive or sarcastic language; respond to the requested kind of help."],
         stops=["The user ends this topic or declines help."],
         prohibited=["Making the decision for the user", "Using shame, threats, or pressure"]),
    dict(key="permission", title="Offer information with permission", chapter="ch6",
         section="ch6.s2.1", starts=["Clients may ask you for information and advice", "Ask permission to offer advice.", "Use the Elicit-Provide-Elicit", "Provide accurate and specific facts", "Elicit responses to such information", "The last step in EPE"],
         objective="Exchange requested, relevant information while respecting permission and user understanding.",
         conditions=["The user has requested information or granted permission.", "Information is within nonclinical competence."],
         moves=["If permission is absent, ask before offering information.", "When permission is explicit, offer concise information and invite the user's reaction."],
         steps=["Check the current request and permission boundary.", "Give only warranted information; distinguish suggestions from facts.", "Leave room for disagreement or refusal."],
         stops=["Permission is refused or withdrawn."],
         prohibited=["Unrequested advice after explicit refusal", "Invented local prices, services, or medical facts"]),
    dict(key="user_plan", title="Build on the user's chosen next step", chapter="ch6",
         section="ch6.s2.1", starts=["Help clients create plans to match", "The plan can be very general", "Create a change plan using a joint process"],
         objective="Help make the user's own chosen small step feasible without replacing it with the assistant's agenda.",
         conditions=["The user wants to plan now.", "A user-owned goal or direction is visible."],
         moves=["Elicit or use the user's own idea.", "Offer one manageable next step, checking fit with stated barriers."],
         steps=["Confirm the chosen direction.", "Translate it into a modest, feasible next action or ask a relevant question."],
         stops=["The user is not ready to plan or only wants listening."],
         prohibited=["Treating an intention as an action already completed", "Prescribing a clinical treatment plan"]),
    dict(key="adjust_after_refusal", title="Adjust after a refusal", chapter="ch3",
         section="ch3.s3.2", starts=["Client sustain talk is often evoked by discord"],
         objective="Respond to an explicit refusal by reducing pressure and changing the conversational approach.",
         conditions=["The user has explicitly rejected advice, a proposal, or a topic."],
         moves=["Acknowledge the refusal without arguing.", "Offer to listen or follow the user's preferred topic; give alternatives only if invited."],
         steps=["Identify what was declined.", "Stop pressing that proposal and follow the new stated boundary."],
         stops=["The user asks to stop the interaction."],
         prohibited=["Repeating the declined proposal as persuasion", "Labeling disagreement as a defect in the user"]),
]


class Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.active, self.paragraphs = [], None, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.stack.append((tag, attrs))
        if tag == "p":
            self.active = dict(ancestors=[a.get("id", "") for _, a in self.stack], text="")

    def handle_data(self, data):
        if self.active is not None:
            self.active["text"] += data

    def handle_endtag(self, tag):
        if self.active is not None and tag == "p":
            self.active["text"] = " ".join(self.active["text"].split())
            self.paragraphs.append(self.active)
            self.active = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                self.stack = self.stack[:i]
                break


def build_skills(source_dir):
    source_dir = Path(source_dir)
    parsed = {}
    for chapter, (filename, book, expected) in SOURCES.items():
        data = (source_dir / filename).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("TIP35 source hash mismatch: " + filename)
        parser = Paragraphs()
        parser.feed(data.decode("utf-8"))
        parsed[chapter] = parser.paragraphs
    records = []
    for definition in DEFINITIONS:
        chapter, section = definition["chapter"], definition["section"]
        filename, book, digest = SOURCES[chapter]
        selected = []
        for start in definition["starts"]:
            matches = [p for p in parsed[chapter] if section in p["ancestors"]
                       and p["text"].startswith(start)
                       and not any(a.startswith("fig") for a in p["ancestors"])]
            if len(matches) != 1:
                raise ValueError("paragraph identity ambiguous: " + start)
            selected.append(matches[0]["text"])
        source_refs = [dict(url=f"https://www.ncbi.nlm.nih.gov/books/{book}/#{section}",
                            section=section, file=filename, file_sha256=digest,
                            paragraph_sha256=hashlib.sha256(p.encode()).hexdigest(),
                            exact_paragraph=p) for p in selected]
        method = (definition["title"] + "\nObjective: " + definition["objective"]
                  + "\nApplicable when: " + " ".join(definition["conditions"])
                  + "\nOptional moves: " + " ".join(definition["moves"])
                  + "\nSteps: " + " ".join(definition["steps"])
                  + "\nStop or change approach when: " + " ".join(definition["stops"])
                  + "\nAvoid: " + "; ".join(definition["prohibited"]) + ".")
        records.append(dict(skill_id="skill:" + definition["key"], version=VERSION,
             original_domain="TIP35 substance-use counseling", adapted_domain="low-risk nonclinical conversation",
             objective=definition["objective"], required_observable_conditions=definition["conditions"],
             exclusions=["Crisis", "Diagnosis", "Treatment advice", "Claims of clinical efficacy"],
             allowed_moves=definition["moves"], conditional_steps=definition["steps"],
             stop_conditions=definition["stops"], prohibited_moves=definition["prohibited"],
             source_refs=source_refs, positive_case_ids=[], negative_case_ids=[], illustrative_case_ids=[],
             review_status="unverified", professional_approved=False, usage_scope="research_only",
             license="TIP35 author text: public domain; third-party exhibits excluded",
             method_reading=method, raw_reading="\n\n".join(selected),
             adaptation_notice="Research adaptation; not a validated professional protocol."))
    return records
