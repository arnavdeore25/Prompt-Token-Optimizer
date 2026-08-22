# Prompt-Token-Optimizer

A tool/web extension that reduces unnecessary tokens while preserving meaning and intent of the prompt.

## Product direction

The extension is not simply a text shortener. Its goal is:

**Minimum tokens required to express maximum intent.**

The MVP:
- removes conversational filler;
- simplifies wordy phrases;
- makes some requirements more explicit;
- removes repeated lines;
- restructures very long "and... and... and..." requirements;
- preserves fenced code blocks;
- never sends prompts to a server in this MVP;
- keeps the original when an optimization would make it longer.

## Supported platforms

- ChatGPT
- Claude
- Gemini

## Privacy

This MVP has no backend and no external API calls. Prompt text is processed inside the content script. Usage statistics are stored locally with Chrome storage.

## Important

This version uses a local, rule-based compression engine. It does **not** send prompts to an external API, so there is no API key or backend required.

The token number is an estimate based on roughly 4 characters per token. It is not an exact tokenizer count.

**Arnav Deore**
MCA Student  
Christ University, Bangalore