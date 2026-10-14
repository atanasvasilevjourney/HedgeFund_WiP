# Portfolio Management Lecture Materials

Research-backed lecture package on portfolio thinking for quantitative traders: escaping the “20-something Modelur” trap, diversification limits, Sharpe optimization pitfalls, factor diversification, and Hierarchical Risk Parity.

## Files

| File | Purpose |
|------|---------|
| `Portfolio_Management_Lecture.docx` | Full lecture notes, appendices (math, worked example, 90-min agenda, exercises), speaker notes |
| `Portfolio_Management_Lecture_Slides.docx` | ~25 slide outlines (import into PowerPoint/Google Slides or present from Word) |
| `Portfolio_Management_Student_Handout.docx` | Short summary + checklist for attendees |

## Regenerate

```bash
python3 scripts/build_portfolio_lecture_docx.py
```

Requires `python-docx` (`pip install python-docx`).

## Primary references

- [Investopedia — illusion of diversification](https://www.investopedia.com/articles/stocks/11/illusion-of-diversification.asp)
- [CFI — Modern Portfolio Theory](https://corporatefinanceinstitute.com/resources/wealth-management/modern-portfolio-theory-mpt/)
- [Wikipedia — Hierarchical Risk Parity](https://en.wikipedia.org/wiki/Hierarchical_Risk_Parity)
