"""Detection patterns shared by the input and output guardrails."""

import re

_I = re.IGNORECASE


def _compile(*patterns: str) -> list[re.Pattern]:
    return [re.compile(p, _I) for p in patterns]


# --- Prompt injection / jailbreak attempts (run on normalised text) -------------------------
INJECTION = _compile(
    # "ignore all previous instructions", "forget your prior rules", "override the system prompt"
    r"\b(?:ignore|disregard|forget|override)\s+(?:(?:all|any|your|the|these|those|my)\s+)*"
    r"(?:previous|prior|above|earlier|preceding|initial|original|system)\s+"
    r"(?:instructions?|rules?|prompts?|directions?|guidelines?|context|messages?)",
    r"\b(?:ignore|disregard|forget)\s+(?:(?:all|any|your|the)\s+)*(?:instructions?|guidelines?|guardrails?)\b",
    # "bypass the guardrails", "disable your safety filters"
    r"\b(?:bypass|disable|circumvent|turn\s+off)\s+(?:(?:all|any|your|the)\s+)*"
    r"(?:guardrails?|safety|content\s+filters?|restrictions?)\b",
    # extracting the hidden prompt
    r"\b(?:reveal|show|print|repeat|display|output|leak|tell\s+me)\b.{0,30}"
    r"\b(?:system|hidden|initial|original|secret)\s+(?:prompt|instructions?|message)",
    r"\b(?:what|which)\s+(?:is|are|were)\s+your\s+(?:system\s+)?(?:instructions?|prompt|rules)\b",
    # persona / mode switching
    r"\byou\s+are\s+now\b",
    r"\bact\s+as\s+(?:an?\s+)?(?:unrestricted|unfiltered|jailbroken|dan)\b",
    r"\bpretend\s+(?:that\s+)?you\s+(?:are|have\s+no)\b",
    r"\b(?:jailbreak|developer\s+mode|do\s+anything\s+now)\b",
    # fake message boundaries / role markers
    r"</?\s*(?:context|document|system|instructions?)\s*>",
    r"<\|[^|>]{1,30}\|>",
    r"\[/?inst\]",
    r"(?:^|\n)\s*(?:system|assistant)\s*:",
    r"\bnew\s+instructions?\s*:",
    # paraphrases
    r"\b(?:ignore|disregard|forget)\s+everything\s+(?:you|above|before|else|that)\b",
    r"\b(?:answer|respond|reply|talk|behave|operate|act)\b.{0,30}\bwithout\s+(?:any\s+)?(?:restrictions?|limits?|rules|filters?)\b",
    r"\bpretend\b.{0,40}\b(?:guardrails?|rules|restrictions?|filters?)\b",
    r"\bwith\s+no\s+(?:rules|restrictions|limits)\b",
    r"\b(?:repeat|print|output|copy)\s+(?:the\s+)?(?:text|words|everything|content|messages?)\s+(?:above|before)\b",
    r"\b(?:translate|summari[sz]e|rephrase|paraphrase|encode|spell)\s+your\s+(?:system\s+)?(?:instructions?|prompt|rules)\b",
    r"\bwhat\s+(?:were|was)\s+you\s+(?:told|instructed|given)\b",
)

# Same idea on text with whitespace/punctuation removed and leetspeak undone, which catches
# "i g n o r e  a l l ..." and "1gn0re all pr3vious ...". Kept to the highest-signal phrases.
INJECTION_SQUASHED = _compile(
    r"(?:ignore|disregard|forget|override)(?:all|any|your|the|these|those|my)*"
    r"(?:previous|prior|above|earlier|preceding|initial|original|system)(?:instructions?|rules?|prompts?|directions?|guidelines?)",
    r"(?:reveal|show|print|repeat|display|output|leak)(?:your|the|me)*(?:system|hidden|initial|original|secret)(?:prompt|instructions?|message)",
    r"bypass(?:the|your|all)*(?:guardrails?|safety|contentfilters?)",
    r"jailbreak|developermode",
)

# --- Requests to cause harm (this bot answers questions; it never needs to help with these) --
HARMFUL_INTENT = _compile(
    r"\b(?:write|create|build|make|generate|develop|code)\b.{0,30}"
    r"\b(?:malware|ransomware|keylogger|computer\s+virus|botnet|rootkit|trojan)\b",
    r"\b(?:launch|run|perform|start|carry\s+out)\b.{0,20}\b(?:ddos|denial[-\s]of[-\s]service)\b",
    r"\b(?:steal|dump|harvest|exfiltrate)\b.{0,30}\b(?:credentials|passwords|api\s+keys|secrets|tokens)\b",
    r"\bhack\s+into\b",
)

# --- Secrets: blocked in user input, redacted from model output ----------------------------
SECRETS = _compile(
    r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",                                        # AWS access key id
    r"-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END[A-Z ]*PRIVATE KEY-----|$)",
    r"\bBearer\s+[A-Za-z0-9\-._~+/]{16,}=*",
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",       # JWT
    r"\bsk-[A-Za-z0-9_-]{20,}\b",                                            # OpenAI-style key
    r"\bgh[pousr]_[A-Za-z0-9]{30,}\b",                                       # GitHub token
    r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b",                                     # Slack token
    r"\b(?:aws[_-]?secret[_-]?access[_-]?key|api[_-]?key|secret|passwd|password|pwd)\s*[:=]\s*\S{6,}",
)

# --- Personal data: redacted from user input, then the question proceeds -----------------------
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def luhn_valid(digits: str) -> bool:
    """Luhn checksum, so ordinary long numbers aren't mistaken for card numbers."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2:
            n = n * 2 - 9 if n * 2 > 9 else n * 2
        total += n
    return total % 10 == 0
