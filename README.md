# MAX Knowledge Base — README

Yeh folder MAX ka personal knowledge base hai.
Koi bhi `.md` file yahan daalo — MAX use padh ke answers dega.

---

## How it works

- Server start hone par sab `.md` files automatically index ho jaati hain
- Jab bhi user koi question kare, MAX pehle yahan search karta hai
- Agar relevant content mile, to wo LLM context mein inject hota hai
- MAX fir usi context se answer deta hai — hallucination kam hota hai

---

## Supported file types

Sirf `.md` (Markdown) files support hain.
Subfolders bhi scan hoti hain (`knowledge/**/*.md`).

---

## Commands

| Bolo MAX ko         | Kya hoga                             |
|---------------------|--------------------------------------|
| "Rebuild knowledge base" | Sab .md files re-index ho jaayengi |
| "Knowledge base list"    | Kaunse docs hain list dikhega       |
| "Knowledge base stats"   | Kitne chunks indexed hain           |
| "Search in knowledge base: X" | Manual search X ke liye     |

---

## Tips for writing good knowledge files

1. **Use headers** (`#`, `##`, `###`) — each header becomes a separate chunk
2. **Keep sections focused** — ek section mein ek topic
3. **Be specific** — vague content kaam nahi karta
4. **File names matter** — descriptive names rakho (e.g., `projects.md`, `client_info.md`)

---

## Example files you can add

```
knowledge/
├── projects.md          ← apne projects ki details
├── clients.md           ← client info, contacts
├── notes.md             ← personal notes
├── code_patterns.md     ← code snippets, patterns
├── meeting_notes.md     ← meeting summaries
└── tech_stack.md        ← tech decisions, architecture
```

---

## Sanket ke liye

Tera current setup:
- ClientDesk CRM: Node.js + Express + MongoDB (₹99/year)
- LinkedIn Automation: Python + Selenium + Groq
- MAX: FastAPI + Groq + ChromaDB

In chizo ke baare mein `.md` files bana aur yahan daalo.
MAX automatically ye sab yaad rakh lega.
