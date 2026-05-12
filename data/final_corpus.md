# Final Corpus: Papers Using LLM/AI as a Tool for Text Annotation

**Selection**: v2 strict screening (DeepSeek V3) | **Date**: 2026-05-12
**Total**: 19 papers from 170 candidates in Public Administration & Policy journals (2023–2026)

## Screening Rationale

The v2 strict prompt was chosen over v3 inclusive prompt because:
- v3 (inclusive) produced 64 AS_TOOL but included many false positives (e.g., papers about general AI topics in low-quality OA journals that don't actually use AI for annotation)
- v2 (strict) produced 19 AS_TOOL with higher precision — each paper has clear evidence of LLM/AI use for text annotation
- The v3 inclusive prompt erred on the side of inclusion, but the noise ratio was too high (47 additional papers, many from Lex localis with generic AI mentions)
- **Principle**: v2's 19 papers are the high-confidence core; borderline cases can be added manually after review

## Paper List

| # | Conf | Task | Year | Journal | Title | Evidence | PDF | MD |
|---|------|------|------|---------|-------|----------|-----|----|
| 1 | 5 | text classification and f | ? | Data & Policy | Tracking policy-relevant narratives of democratic resilience at scale: From expe | The paper demonstrates the use of LLMs to label populism in texts (Section 5.1) and to analyze immigration framing via paired-completion (Section 5.2) | Y | Y |
| 2 | 5 | topic modeling | ? | Journal of Social Policy | Subsidising silence: how policy ideas entrench Italy’s use of employment subsidi | We map stakeholder narratives in national media using Natural Language Processing techniques (BERTopic) and analyse parliamentary debates to identify  | Y | Y |
| 3 | 5 | term generation for codin | ? | Public Administration and Developme | The Politics of Policy Robustness: A Central Paradox and Computational Review of | For this purpose, we compiled a comprehensive list of key terms associated with each theory based on existing literature, a systematic scan of terms a | Y | Y |
| 4 | 5 | emotionality classificati | ? | Journal of Public Administration Re | Inequality in frontline communication: bureaucrats talk differently to men and w | We measure the linguistic complexity and emotionality in administrative communication, using a mixture of machine learning-based text classification a | Y | Y |
| 5 | 5 | frame classification | ? | Journal of European Public Policy | Crisis-exploitation or fear-mongering? A research agenda for the comparative stu | We define and measure illiberal frames ... using a novel IPF codebook and state-of-the-art large language models. ... For fine-tuning new LLMs and pro | Y | Y |
| 6 | 5 | classification | ? | Regulation & Governance | Mapping Green Skills in Collective Skill Formation Systems: A Natural Language P | We employed a LLM from OpenAI to validate and extend the classification process. Each of the 63,751 individually listed skills was classified using th | Y | Y |
| 7 | 5 | sentiment analysis | ? | Journal of Public Administration Re | A reputational perspective on structural reforms: how media reputations are rela | This study uses novel and advanced BERT language models to detect attributions of responsibility for positive/negative outcomes in media coverage towa | Y | Y |
| 8 | 5 | text classification | ? | Public Administration Review | Building an evidence engine to promote more responsive government | The GWCM PMO leveraged the free-form vendor’s description to assign products within the new detailed taxonomy using a form of machine learning called  | Y | Y |
| 9 | 5 | information extraction | ? | Global Public Policy and Governance | Combating corruption on the frontlines: analyzing penalties for street-level bur | Using text mining techniques and natural language processing (NLP) tools, we identified the details of corruption cases... We used named entity recogn | Y | Y |
| 10 | 5 | topic labeling | ? | Review of Policy Research | The interface between research funding and environmental policies in an emergent | Then, the ChatGPT API, GPT-4, was employed to generate labels for these topics, guided by a prompt that considered both the keywords and representativ | Y | Y |
| 11 | 5 | classification of message | ? | Journal of Public Policy & Marketin | Finding the Right Voice: How CEO Communication on the Russia-Ukraine War Drives  | Leveraging the capabilities of BERT, we identified the framing and appeal within CEO and brand messages | Y | Y |
| 12 | 5 | classification | ? | Data & Policy | AI-assisted prescreening of biomedical research proposals: ethical consideration | The prescreening comprises three NLP models working independently; these are BioLinkBERT-Base, BioELECTRA-Base, and BioLinkBERT-Base incorporating Ada | Y | Y |
| 13 | 5 | topic modeling | ? | Data & Policy | Developing AI predictive migration tools to enhance humanitarian support: The ca | In the vectorization step, the transformation of text data into numeric vectors takes place. Following this, every topic vector is passed through the  | Y | Y |
| 14 | 5 | content analysis | ? | Data & Policy | Understanding to intervene: The codesign of text classifiers with peace practiti | The LLM offers the advantages of being more efficient in identifying affective polarization instances because of its improved context awareness... | Y | Y |
| 15 | 5 | text analysis | ? | Regulation & Governance | Noisy Politics, Quiet Technocrats: Strategic Silence by Central Banks | The paper uses large language models (LLMs) and natural language processing (NLP) to analyze central bank speeches. Specifically, it mentions 'natural | Y | Y |
| 16 | 5 | scale development and syn | ? | Public Administration Review | Re‐Imagining the Epistemic Possibilities of <scp>GPT</scp> for Public Administra | The paper uses GPT to generate dictionaries for measuring innovation, impact, and replicability in text analysis (scale development) and to generate s | Y | Y |
| 17 | 5 | other | ? | Data & Policy | SyROCCo: enhancing systematic reviews using machine learning | The paper uses machine learning techniques (text classification, named entity recognition, semantic text similarity) to assist in systematic review ta | Y | Y |
| 18 | 5 | content analysis | ? | Data & Policy | Uncovering policy priorities for disability inclusion: NLP and LLM approaches to | The paper uses GenAI tools (Gemini 1.5 Flash, GPT-4o, NotebookLM) to analyze a subset of CRPD State Reports, performing tasks such as identifying impo | Y | Y |
| 19 | 4 | sentiment and content ana | ? | Data & Policy | Joining forces for online feedback management: policy recommendations for human– | It includes a customized sentiment and content analysis engine that automatically identifies and classifies aspects in guest-written online reviews. | Y | Y |

## File Paths

**1. Tracking policy-relevant narratives of democratic resilience at scale: From expe**
  DOI: https://doi.org/10.1017/dap.2026.10063
  PDF: data/pdfs/10_1017_dap_2026_10063.pdf
  MD:  data/extracted_text/10_1017_dap_2026_10063.md

**2. Subsidising silence: how policy ideas entrench Italy’s use of employment subsidi**
  DOI: https://doi.org/10.1017/s0047279426101378
  PDF: data/pdfs/10_1017_s0047279426101378.pdf
  MD:  data/extracted_text/10_1017_s0047279426101378.md

**3. The Politics of Policy Robustness: A Central Paradox and Computational Review of**
  DOI: https://doi.org/10.1002/pad.70054
  PDF: data/pdfs/10_1002_pad_70054.pdf
  MD:  data/extracted_text/10_1002_pad_70054.md

**4. Inequality in frontline communication: bureaucrats talk differently to men and w**
  DOI: https://doi.org/10.1093/jopart/muaf036
  PDF: data/pdfs/10_1093_jopart_muaf036.pdf
  MD:  data/extracted_text/10_1093_jopart_muaf036.md

**5. Crisis-exploitation or fear-mongering? A research agenda for the comparative stu**
  DOI: https://doi.org/10.1080/13501763.2025.2583176
  PDF: data/pdfs/10_1080_13501763_2025_2583176.pdf
  MD:  data/extracted_text/10_1080_13501763_2025_2583176.md

**6. Mapping Green Skills in Collective Skill Formation Systems: A Natural Language P**
  DOI: https://doi.org/10.1111/rego.70097
  PDF: data/pdfs/10_1111_rego_70097.pdf
  MD:  data/extracted_text/10_1111_rego_70097.md

**7. A reputational perspective on structural reforms: how media reputations are rela**
  DOI: https://doi.org/10.1093/jopart/muae023
  PDF: data/pdfs/10_1093_jopart_muae023.pdf
  MD:  data/extracted_text/10_1093_jopart_muae023.md

**8. Building an evidence engine to promote more responsive government**
  DOI: https://doi.org/10.1111/puar.13880
  PDF: data/pdfs/10_1111_puar_13880.pdf
  MD:  data/extracted_text/10_1111_puar_13880.md

**9. Combating corruption on the frontlines: analyzing penalties for street-level bur**
  DOI: https://doi.org/10.1007/s43508-024-00096-3
  PDF: data/pdfs/10_1007_s43508-024-00096-3.pdf
  MD:  data/extracted_text/10_1007_s43508-024-00096-3.md

**10. The interface between research funding and environmental policies in an emergent**
  DOI: https://doi.org/10.1111/ropr.12630
  PDF: data/pdfs/10_1111_ropr_12630.pdf
  MD:  data/extracted_text/10_1111_ropr_12630.md

**11. Finding the Right Voice: How CEO Communication on the Russia-Ukraine War Drives **
  DOI: https://doi.org/10.1177/07439156241230910
  PDF: data/pdfs/10_1177_07439156241230910.pdf
  MD:  data/extracted_text/10_1177_07439156241230910.md

**12. AI-assisted prescreening of biomedical research proposals: ethical consideration**
  DOI: https://doi.org/10.1017/dap.2024.41
  PDF: data/pdfs/10_1017_dap_2024_41.pdf
  MD:  data/extracted_text/10_1017_dap_2024_41.md

**13. Developing AI predictive migration tools to enhance humanitarian support: The ca**
  DOI: https://doi.org/10.1017/dap.2024.76
  PDF: data/pdfs/10_1017_dap_2024_76.pdf
  MD:  data/extracted_text/10_1017_dap_2024_76.md

**14. Understanding to intervene: The codesign of text classifiers with peace practiti**
  DOI: https://doi.org/10.1017/dap.2024.44
  PDF: data/pdfs/10_1017_dap_2024_44.pdf
  MD:  data/extracted_text/10_1017_dap_2024_44.md

**15. Noisy Politics, Quiet Technocrats: Strategic Silence by Central Banks**
  DOI: https://doi.org/10.1111/rego.70052
  PDF: data/pdfs/10_1111_rego_70052.pdf
  MD:  data/extracted_text/10_1111_rego_70052.md

**16. Re‐Imagining the Epistemic Possibilities of <scp>GPT</scp> for Public Administra**
  DOI: https://doi.org/10.1111/puar.70098
  PDF: data/pdfs/10_1111_puar_70098.pdf
  MD:  data/extracted_text/10_1111_puar_70098.md

**17. SyROCCo: enhancing systematic reviews using machine learning**
  DOI: https://doi.org/10.1017/dap.2024.33
  PDF: data/pdfs/10_1017_dap_2024_33.pdf
  MD:  data/extracted_text/10_1017_dap_2024_33.md

**18. Uncovering policy priorities for disability inclusion: NLP and LLM approaches to**
  DOI: https://doi.org/10.1017/dap.2025.10017
  PDF: data/pdfs/10_1017_dap_2025_10017.pdf
  MD:  data/extracted_text/10_1017_dap_2025_10017.md

**19. Joining forces for online feedback management: policy recommendations for human–**
  DOI: https://doi.org/10.1017/dap.2025.13
  PDF: data/pdfs/10_1017_dap_2025_13.pdf
  MD:  data/extracted_text/10_1017_dap_2025_13.md

