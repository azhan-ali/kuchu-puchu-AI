"""
core/diagram_generator.py
Dedicated module for generating and sanitizing renderable Mermaid.js Mind Maps and Flowcharts
using LangChain with Gemini (and Groq fallback).
"""

import os
import re
import time
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

# Set of reserved Mermaid keywords that must not be used as standalone node IDs
RESERVED_NODE_IDS = {
    "end", "subgraph", "graph", "flowchart", "style", "classdef", "class",
    "click", "direction", "interpolate", "linkstyle"
}

_diagram_llm_instance = None

def get_diagram_llm():
    """
    Returns the most reliable LLM for diagram generation.
    Prioritizes Gemini 2.5 Flash, falling back to Groq if Gemini key is missing or fails.
    """
    global _diagram_llm_instance
    if _diagram_llm_instance is not None:
        return _diagram_llm_instance

    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            _diagram_llm_instance = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                api_key=gemini_key,
                temperature=0.1
            )
            return _diagram_llm_instance
        except Exception as e:
            print(f"[diagram_generator] Warning: Failed to initialize ChatGoogleGenerativeAI: {e}")

    # Fallback to Groq
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            from langchain_groq import ChatGroq
            _diagram_llm_instance = ChatGroq(
                model="openai/gpt-oss-120b",
                api_key=groq_key,
                temperature=0.1
            )
            return _diagram_llm_instance
        except Exception as e:
            print(f"[diagram_generator] Warning: Failed to initialize ChatGroq: {e}")

    # Fallback to Mistral
    mistral_key = os.getenv("MISTRAL_API_KEY")
    if mistral_key:
        try:
            from langchain_mistralai import ChatMistralAI
            _diagram_llm_instance = ChatMistralAI(
                model="mistral-small-latest",
                mistral_api_key=mistral_key,
                temperature=0.1
            )
            return _diagram_llm_instance
        except Exception as e:
            print(f"[diagram_generator] Warning: Failed to initialize ChatMistralAI: {e}")

    return None


def extract_topic_hint(transcript: str) -> str:
    """Extracts a short, clean topic name from transcript text for fallbacks."""
    if not transcript or not transcript.strip():
        return "Meeting Overview"

    first_chunk = transcript[:300].strip()
    first_line = first_chunk.split("\n")[0]
    clean_line = re.sub(r'[^a-zA-Z0-9\s]', ' ', first_line)
    words = [w for w in clean_line.split() if len(w) > 2]
    if words:
        hint = " ".join(words[:4]).title()
        if len(hint) <= 30:
            return hint
    return "Meeting Discussion"


def build_dynamic_mindmap_fallback(transcript: str) -> str:
    """Constructs a context-aware Mermaid mindmap directly from transcript sentences."""
    topic = extract_topic_hint(transcript)
    
    # Extract clean sentence fragments
    sentences = [s.strip() for s in re.split(r'[.!?\n]+', transcript) if len(s.strip()) > 15]
    
    cat1_items = []
    cat2_items = []
    cat3_items = []

    for s in sentences[:9]:
        clean_s = re.sub(r'[^a-zA-Z0-9\s]', ' ', s)
        clean_s = re.sub(r'\s+', ' ', clean_s).strip()
        words = clean_s.split()
        if words:
            short_phrase = " ".join(words[:4]).title()
            if len(cat1_items) < 2:
                cat1_items.append(short_phrase)
            elif len(cat2_items) < 2:
                cat2_items.append(short_phrase)
            elif len(cat3_items) < 2:
                cat3_items.append(short_phrase)

    if not cat1_items:
        cat1_items = ["Overview and Scope", "Primary Objectives"]
    if not cat2_items:
        cat2_items = ["Key Discussion", "Important Details"]
    if not cat3_items:
        cat3_items = ["Action Items", "Target Milestones"]

    lines = [
        "mindmap",
        f"  root(({topic}))",
        "    Core Objectives",
        *[f"      {item}" for item in cat1_items],
        "    Key Discussion Topics",
        *[f"      {item}" for item in cat2_items],
        "    Decisions and Execution",
        *[f"      {item}" for item in cat3_items]
    ]
    return "\n".join(lines)


def build_dynamic_flowchart_fallback(transcript: str) -> str:
    """Constructs a context-aware Mermaid flowchart directly from transcript sentences."""
    sentences = [s.strip() for s in re.split(r'[.!?\n]+', transcript) if len(s.strip()) > 12]
    steps = []
    for s in sentences[:6]:
        clean_s = re.sub(r'[^a-zA-Z0-9\s]', ' ', s)
        clean_s = re.sub(r'\s+', ' ', clean_s).strip()
        words = clean_s.split()
        if len(words) >= 2:
            step_text = " ".join(words[:6]).title()
            steps.append(step_text)

    if len(steps) < 3:
        topic = extract_topic_hint(transcript)
        steps = [
            f"Initialize: {topic}",
            "Review Requirements and Scope",
            "Execute Discussion Points",
            "Evaluate Decisions and Actions",
            "Finalize Deliverables and Follow Up"
        ]

    lines = ["graph TD"]
    for i in range(len(steps) - 1):
        if i == len(steps) - 2 and len(steps) >= 4:
            # Add a decision node for realistic workflow
            lines.append(f'    step_{i}["{steps[i]}"] --> dec_eval{{"Are Requirements Met?"}}')
            lines.append(f'    dec_eval -->|Yes| step_{i+1}["{steps[i+1]}"]')
            lines.append(f'    dec_eval -->|No| step_{max(0, i-1)}')
        else:
            lines.append(f'    step_{i}["{steps[i]}"] --> step_{i+1}["{steps[i+1]}"]')

    return "\n".join(lines)


def sanitize_mindmap(text: str, fallback_topic: str = "Meeting Analysis") -> str:
    """
    Sanitizes raw LLM output into strictly valid, renderable Mermaid.js Mindmap syntax.
    Enforces correct indentation, strips illegal brackets, quotes, and punctuation.
    """
    if not text or not text.strip():
        return build_dynamic_mindmap_fallback(fallback_topic)

    # Remove code fences and preamble
    cleaned = re.sub(r'```(?:mermaid)?', '', text).strip()
    lines = cleaned.splitlines()

    sanitized_lines = ["mindmap"]
    has_root = False
    prev_indent = 2
    branch_count = 0

    clean_fallback = re.sub(r'[^a-zA-Z0-9\s]', ' ', fallback_topic)
    clean_fallback = re.sub(r'\s+', ' ', clean_fallback).strip() or "Discussion Overview"
    if len(clean_fallback) > 35:
        clean_fallback = clean_fallback[:35].rsplit(' ', 1)[0]

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line:
            continue

        # Skip bare "mindmap" keyword in body
        if line.strip().lower() == "mindmap":
            continue

        expanded = line.replace('\t', '  ')
        leading_spaces = len(expanded) - len(expanded.lstrip())
        content = expanded.strip()

        # Handle root node
        if not has_root:
            root_match = re.search(
                r'root(?:\(\((.*?)\)\)|\((.*?)\)|\[(.*?)\]|:\s*(.*?)|(?:\s+(.*)))',
                content,
                re.IGNORECASE
            )
            root_title = ""
            if root_match:
                for grp in root_match.groups():
                    if grp:
                        root_title = grp.strip()
                        break
            if not root_title:
                root_title = content

            root_title = re.sub(r'[^a-zA-Z0-9\s\-]', ' ', root_title)
            root_title = re.sub(r'\s+', ' ', root_title).strip()
            if not root_title:
                root_title = clean_fallback

            sanitized_lines.append(f"  root(({root_title}))")
            has_root = True
            prev_indent = 2
            continue

        # Clean branch / leaf node content
        # Remove bullet marks (e.g. -, *, +, 1.)
        node_text = re.sub(r'^(?:[\-\*\+•]|\d+[\.\)])\s*', '', content).strip()
        # Remove shape delimiters, quotes, colons, and illegal characters
        node_text = re.sub(r'[()\[\]{}"\'`:;\\|`~^<>*/]', ' ', node_text)
        node_text = re.sub(r'\s+', ' ', node_text).strip()

        if not node_text:
            continue

        # Limit node length for clean rendering
        if len(node_text) > 45:
            node_text = node_text[:45].rsplit(' ', 1)[0]

        # Calculate indentation: at least 4 spaces, increment by 2
        indent = max(4, (leading_spaces // 2) * 2)
        if indent > prev_indent + 2:
            indent = prev_indent + 2

        prev_indent = indent
        sanitized_lines.append(" " * indent + node_text)
        branch_count += 1

    if not has_root or branch_count < 2:
        return build_dynamic_mindmap_fallback(fallback_topic)

    return "\n".join(sanitized_lines)


def split_outside_brackets(line: str):
    """
    Splits a line into (node, arrow, node, arrow, ...) strictly matching arrows
    that appear OUTSIDE of brackets [] {} () and quotes "" ''.
    """
    arrow_re = re.compile(r'^(?:-->|->|==>|-\.->)(?:\|.*?\|)?')
    tokens = []
    current_token = []
    i = 0
    n = len(line)
    in_quote = False
    quote_char = ''
    bracket_depth = 0

    while i < n:
        ch = line[i]
        if ch in ('"', "'"):
            if not in_quote:
                in_quote = True
                quote_char = ch
            elif ch == quote_char:
                in_quote = False
            current_token.append(ch)
            i += 1
            continue

        if not in_quote:
            if ch in ('[', '{', '('):
                bracket_depth += 1
                current_token.append(ch)
                i += 1
                continue
            elif ch in (']', '}', ')'):
                if bracket_depth > 0:
                    bracket_depth -= 1
                current_token.append(ch)
                i += 1
                continue

            if bracket_depth == 0:
                match = arrow_re.match(line[i:])
                if match:
                    node_text = "".join(current_token).strip()
                    if node_text:
                        tokens.append(node_text)
                    current_token = []
                    arrow_text = match.group(0).strip()
                    tokens.append(arrow_text)
                    i += match.end()
                    continue

        current_token.append(ch)
        i += 1

    last_text = "".join(current_token).strip()
    if last_text:
        tokens.append(last_text)
    return tokens


def sanitize_flowchart(text: str, fallback_topic: str = "Process Workflow") -> str:
    """
    Sanitizes raw LLM output into strictly valid, renderable Mermaid.js Flowchart syntax.
    Enforces safe node IDs, valid quoted labels, standard arrows, and strips unsupported syntax.
    """
    if not text or not text.strip():
        return build_dynamic_flowchart_fallback(fallback_topic)

    cleaned = re.sub(r'```(?:mermaid)?', '', text).strip()
    lines = cleaned.splitlines()

    sanitized_lines = ["graph TD"]
    valid_links_count = 0

    clean_fallback = re.sub(r'[^a-zA-Z0-9\s]', ' ', fallback_topic)
    clean_fallback = re.sub(r'\s+', ' ', clean_fallback).strip() or "Workflow"
    if len(clean_fallback) > 30:
        clean_fallback = clean_fallback[:30].rsplit(' ', 1)[0]

    def get_safe_id(raw_id: str) -> str:
        s_id = re.sub(r'[^a-zA-Z0-9_]', '_', raw_id.strip()).strip('_')
        if not s_id or s_id.lower() in RESERVED_NODE_IDS:
            s_id = f"node_{s_id}" if s_id else "node_step"
        return s_id

    def sanitize_label(label: str) -> str:
        l = label.strip()
        if (l.startswith('"') and l.endswith('"')) or (l.startswith("'") and l.endswith("'")):
            l = l[1:-1].strip()
        l = l.replace('"', "'").replace('`', '').replace('\\', ' ')
        l = l.replace('-->', 'to').replace('->', 'to')
        l = re.sub(r'[\r\n]+', ' ', l)
        l = re.sub(r'\s+', ' ', l).strip()
        if len(l) > 65:
            l = l[:65].rsplit(' ', 1)[0]
        return l or "Step"

    def format_node_part(part: str) -> str:
        part = part.strip()
        if not part:
            return ""

        # Match id["label"] or id[label]
        box_match = re.match(r'^([A-Za-z0-9_]+)\s*\[(.*?)\]$', part, re.DOTALL)
        if box_match:
            nid, lbl = box_match.groups()
            return f'{get_safe_id(nid)}["{sanitize_label(lbl)}"]'

        # Match id{"label"} or id{label}
        dec_match = re.match(r'^([A-Za-z0-9_]+)\s*\{(.*?)\}$', part, re.DOTALL)
        if dec_match:
            nid, lbl = dec_match.groups()
            return f'{get_safe_id(nid)}{{"{sanitize_label(lbl)}"}}'

        # Match id("label") or id(label)
        rnd_match = re.match(r'^([A-Za-z0-9_]+)\s*\((.*?)\)$', part, re.DOTALL)
        if rnd_match:
            nid, lbl = rnd_match.groups()
            return f'{get_safe_id(nid)}("{sanitize_label(lbl)}")'

        # Match id(("label"))
        circ_match = re.match(r'^([A-Za-z0-9_]+)\s*\(\((.*?)\)\)$', part, re.DOTALL)
        if circ_match:
            nid, lbl = circ_match.groups()
            return f'{get_safe_id(nid)}(("{sanitize_label(lbl)}"))'

        # If it has spaces, turn it into safe_id["label"]
        if ' ' in part:
            safe_id = get_safe_id(part)
            return f'{safe_id}["{sanitize_label(part)}"]'

        return get_safe_id(part)

    for line in lines:
        line_str = line.strip().rstrip(';')
        if not line_str:
            continue

        # Skip bullet prefixes
        line_str = re.sub(r'^(?:[\-\*\+•]|\d+[\.\)])\s*', '', line_str).strip()

        # Skip headers
        if re.match(r'^(?:graph|flowchart)\s+[A-Za-z]+', line_str, re.IGNORECASE):
            continue

        # Skip unsupported subgraphs/styles
        if re.match(r'^(?:subgraph|style|classDef|class|linkStyle)\b', line_str, re.IGNORECASE):
            continue
        if line_str.lower() == "end":
            continue

        tokens = split_outside_brackets(line_str)
        if len(tokens) == 1:
            # Standalone node definitions
            formatted = format_node_part(tokens[0])
            if formatted and ('[' in formatted or '{' in formatted or '(' in formatted):
                sanitized_lines.append(f"    {formatted}")
        elif len(tokens) >= 3:
            new_line_parts = []
            for i, token in enumerate(tokens):
                if i % 2 == 0:
                    formatted = format_node_part(token)
                    if formatted:
                        new_line_parts.append(formatted)
                else:
                    arrow_tok = token.strip()
                    edge_match = re.search(r'\|(.*?)\|', arrow_tok)
                    if edge_match:
                        clean_edge = re.sub(r'[^a-zA-Z0-9\s\?]', '', edge_match.group(1)).strip()
                        clean_edge = clean_edge.replace('"', '')
                        new_line_parts.append(f"-->|{clean_edge}|")
                    else:
                        new_line_parts.append("-->")

            if len(new_line_parts) >= 3:
                sanitized_lines.append("    " + " ".join(new_line_parts))
                valid_links_count += 1

    if valid_links_count == 0:
        return build_dynamic_flowchart_fallback(fallback_topic)

    return "\n".join(sanitized_lines)


def generate_mind_map(transcript: str) -> str:
    """
    Generates a structured Mermaid.js mind map from a meeting/video transcript.
    Uses Gemini (with Groq fallback) and returns strictly validated Mermaid syntax.
    """
    if not transcript or not transcript.strip():
        return build_dynamic_mindmap_fallback("No Transcript Available")

    topic_hint = extract_topic_hint(transcript)
    llm = get_diagram_llm()

    if not llm:
        print("[diagram_generator] No LLM available, generating dynamic mindmap from transcript.")
        return build_dynamic_mindmap_fallback(transcript)

    # Use first 4000 characters to focus on the structure without hitting token boundaries
    focused_transcript = transcript[:4500]

    system_prompt = (
        "You are an expert data visualizer and technical architect specializing in Mermaid.js diagrams.\n"
        "Create an insightful, hierarchical mind map summarizing the core ideas, themes, and subtopics from the transcript.\n\n"
        "STRICT MERMAID MINDMAP RULES:\n"
        "1. Start the first line with exactly: mindmap\n"
        "2. Line 2 must be the root node indented by 2 spaces:   root((Central Topic Title))\n"
        "3. Main branch nodes must be indented by 4 spaces (e.g.     Main Topic 1)\n"
        "4. Sub-branch nodes must be indented by 6 spaces (e.g.       Subtopic A)\n"
        "5. Deepest details indented by 8 spaces (e.g.         Detail 1)\n"
        "6. Do NOT use parentheses (), square brackets [], curly braces {}, colons :, or quotes \" ' in branch nodes.\n"
        "7. Only use plain alphanumeric words for branch node text.\n"
        "8. Keep each node short and punchy (1 to 5 words).\n"
        "9. Output ONLY raw Mermaid syntax. Do NOT wrap in markdown fences (```mermaid) or include any prose."
    )

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Transcript:\n{focused_transcript}")
        ])
        raw_text = response.content if hasattr(response, "content") else str(response)
        return sanitize_mindmap(raw_text, fallback_topic=topic_hint)
    except Exception as e:
        print(f"[diagram_generator] Error invoking LLM for mind map: {e}")
        return build_dynamic_mindmap_fallback(transcript)


def generate_flowchart(transcript: str) -> str:
    """
    Generates a structured Mermaid.js process flowchart from a meeting/video transcript.
    Uses Gemini (with Groq fallback) and returns strictly validated Mermaid syntax.
    """
    if not transcript or not transcript.strip():
        return build_dynamic_flowchart_fallback("No Transcript Available")

    topic_hint = extract_topic_hint(transcript)
    llm = get_diagram_llm()

    if not llm:
        print("[diagram_generator] No LLM available, generating dynamic flowchart from transcript.")
        return build_dynamic_flowchart_fallback(transcript)

    focused_transcript = transcript[:4500]

    system_prompt = (
        "You are an expert systems analyst specializing in Mermaid.js process diagrams.\n"
        "Extract the logical chronological process, workflow, sequence of operations, or decisions from the transcript.\n\n"
        "STRICT MERMAID FLOWCHART RULES:\n"
        "1. First line must be exactly: graph TD\n"
        "2. Use clean alphanumeric identifiers for nodes: step1, step2, dec1, step3, finalStep.\n"
        "3. NEVER use reserved words like 'start', 'end', 'graph', 'subgraph', 'style' as node IDs.\n"
        "4. Always enclose node text in double quotes inside brackets: step1[\"Step Description\"]\n"
        "5. For decision or conditional nodes, use braces with quotes: dec1{\"Condition or question?\"}\n"
        "6. Connect nodes with arrows: step1 --> step2\n"
        "7. For decision branches, use labeled arrows: dec1 -->|Yes| step3\n"
        "8. Do not use quotes or backticks inside the label text.\n"
        "9. Output ONLY raw Mermaid syntax. Do NOT wrap in markdown fences (```mermaid) or include any prose."
    )

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Transcript:\n{focused_transcript}")
        ])
        raw_text = response.content if hasattr(response, "content") else str(response)
        return sanitize_flowchart(raw_text, fallback_topic=topic_hint)
    except Exception as e:
        print(f"[diagram_generator] Error invoking LLM for flowchart: {e}")
        return build_dynamic_flowchart_fallback(transcript)
