"""
Resume & Skill Matcher Module
=============================
Matches job descriptions against the master profile in profile.json,
calculates match scores, identifies missing skills, and generates
tailored resumes (LaTeX .tex + PDF) and customized cover letters
using Qwen2.5-3B-Instruct AI or deterministic templates.
"""

import os
import re
import html
import json
from pathlib import Path
from typing import Any

from scripts.llm_assistant import LLMAssistant

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PROFILE_PATH = _REPO_ROOT / "profile.json"
_OUTPUT_DIR = _REPO_ROOT / "generated_resumes"
_OUTPUT_DIR.mkdir(exist_ok=True)


def escape_latex(s: Any) -> str:
    """Escape LaTeX special characters (&, %, $, #, _, {, }, ~, ^, \\)."""
    if s is None:
        return ""
    text = str(s)
    conv = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    pattern = re.compile("|".join(re.escape(k) for k in conv.keys()))
    return pattern.sub(lambda m: conv[m.group()], text)


class ResumeBuilder:
    """Handles skill extraction, scoring, and tailored document generation."""

    def __init__(self, profile_path: Path | str | None = None):
        self.profile_path = Path(profile_path or _PROFILE_PATH)
        self.profile = self.load_profile()
        self.llm = LLMAssistant(self.profile)

    def load_profile(self) -> dict[str, Any]:
        """Load user profile from JSON."""
        if not self.profile_path.exists():
            return {
                "personal": {"name": "Candidate", "email": "candidate@example.com"},
                "skills": [],
                "projects": [],
                "experience": [],
                "education": [],
                "qa_bank": {},
            }
        with open(self.profile_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def extract_keywords_from_text(self, text: str) -> set[str]:
        """Extract potential tech keywords and skills from text."""
        if not text:
            return set()

        clean = re.sub(r"[^\w\+\#\.\-]", " ", text.lower())
        tokens = set(clean.split())

        known_tech = [
            "python", "javascript", "typescript", "react", "next.js", "nextjs",
            "fastapi", "django", "flask", "node.js", "nodejs", "express",
            "sql", "postgresql", "postgres", "sqlite", "mysql", "mongodb", "redis",
            "docker", "kubernetes", "aws", "gcp", "azure", "ci/cd", "git",
            "graphql", "rest", "rest api", "html", "css", "tailwind", "playwright",
            "selenium", "puppeteer", "linux", "c++", "c#", "java", "golang", "go",
            "microservices", "pandas", "numpy", "machine learning", "ml", "ai",
            "deep learning", "nlp", "llm", "pytest", "unit testing", "agile",
            "qwen", "hugging face", "pytorch", "tensorflow",
        ]

        found = set()
        text_lower = text.lower()
        for tech in known_tech:
            pattern = r"\b" + re.escape(tech) + r"\b"
            if re.search(pattern, text_lower):
                found.add(tech)

        return found

    def match_job(self, job_title: str, job_description: str) -> dict[str, Any]:
        """
        Analyze JD and calculate match score against master profile.
        Returns match percentage, matched skills, missing skills,
        and recommended projects.
        """
        combined_text = f"{job_title or ''} {job_description or ''}"
        jd_keywords = self.extract_keywords_from_text(combined_text)

        user_skills_list = [
            s["name"] if isinstance(s, dict) else str(s)
            for s in self.profile.get("skills", [])
        ]
        user_skills_lower = {s.lower(): s for s in user_skills_list}

        matched_skills: list[str] = []
        missing_skills: list[str] = []

        for kw in sorted(jd_keywords):
            matched = False
            for u_lower, orig in user_skills_lower.items():
                if kw in u_lower or u_lower in kw:
                    if orig not in matched_skills:
                        matched_skills.append(orig)
                    matched = True
                    break
            if not matched:
                missing_skills.append(kw.title())

        for u_lower, orig in user_skills_lower.items():
            if re.search(r"\b" + re.escape(u_lower) + r"\b", combined_text.lower()):
                if orig not in matched_skills:
                    matched_skills.append(orig)

        master_projects = self.profile.get("projects", [])
        scored_projects = []
        for p in master_projects:
            tags = [t.lower() for t in p.get("tags", [])]
            overlap = sum(1 for t in tags if any(t in kw or kw in t for kw in jd_keywords))
            scored_projects.append((overlap, p))

        scored_projects.sort(key=lambda x: x[0], reverse=True)
        recommended_projects = [p for _, p in scored_projects[:3]]

        total_eval = len(matched_skills) + len(missing_skills)
        if total_eval > 0:
            match_score = int(round((len(matched_skills) / total_eval) * 100))
        else:
            match_score = 75

        match_score = max(30, min(98, match_score))

        return {
            "match_score": match_score,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills[:8],
            "all_user_skills": user_skills_list,
            "recommended_projects": recommended_projects,
            "job_title": job_title,
        }

    async def tailor_with_ai(
        self,
        job_title: str,
        company: str,
        job_description: str,
        active_skills: list[str],
    ) -> dict[str, Any]:
        """
        Use Qwen2.5-3B-Instruct to create a tailored summary, optimized
        experience bullets, and a customized cover letter for this job.
        """
        tailored_summary = await self.llm.tailor_summary(
            job_title=job_title,
            company=company,
            job_description=job_description,
            matched_skills=active_skills,
        )

        orig_experience = self.profile.get("experience", [])
        tailored_experience = await self.llm.tailor_experience_bullets(
            job_title=job_title,
            company=company,
            job_description=job_description,
            matched_skills=active_skills,
            experience_items=orig_experience,
        )

        cover_letter = await self.llm.generate_cover_letter(
            job_title=job_title,
            company=company,
            job_description=job_description,
            matched_skills=active_skills,
        )

        return {
            "summary": tailored_summary,
            "experience": tailored_experience,
            "cover_letter": cover_letter,
        }

    def generate_latex_resume(
        self,
        job_title: str,
        company: str,
        active_skills: list[str],
        selected_projects: list[dict[str, Any]] | None = None,
        custom_summary: str | None = None,
        custom_experience: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate tailored LaTeX resume code."""
        personal = self.profile.get("personal", {})
        name = escape_latex(personal.get("name", "Applicant"))
        email = escape_latex(personal.get("email", ""))
        phone = escape_latex(personal.get("phone", ""))
        location = escape_latex(personal.get("location", ""))
        linkedin = personal.get("linkedin_url", "")
        github = personal.get("github_url", "")

        safe_job_title = escape_latex(job_title)
        safe_company = escape_latex(company)
        summary_text = custom_summary or self.profile.get("summary", "")
        safe_summary = escape_latex(summary_text)
        safe_skills = ", ".join(escape_latex(s) for s in active_skills)

        projects = selected_projects or self.profile.get("projects", [])[:3]
        experience = custom_experience if custom_experience is not None else self.profile.get("experience", [])
        education = self.profile.get("education", [])

        latex = r"""\documentclass[letterpaper,10pt]{article}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage{marvosym}
\usepackage[usenames,dvipsnames]{color}
\usepackage{verbatim}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\usepackage[english]{babel}
\usepackage{tabularx}

\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}

\addtolength{\oddsidemargin}{-0.5in}
\addtolength{\evensidemargin}{-0.5in}
\addtolength{\textwidth}{1.0in}
\addtolength{\topmargin}{-0.5in}
\addtolength{\textheight}{1.0in}

\urlstyle{same}
\raggedbottom
\raggedright
\setlength{\tabcolsep}{0in}

\titleformat{\section}{
  \vspace{-4pt}\scshape\raggedright\large
}{}{0em}{}[\color{black}\titlerule \vspace{-5pt}]

\begin{document}

%----------HEADING----------
\begin{center}
    \textbf{\Huge \scshape """ + name + r"""} \\ \vspace{2pt}
    \small """ + f"{location} $|$ {phone} $|$ \\href{{mailto:{email}}}{{{email}}} $|$ \\href{{{linkedin}}}{{LinkedIn}} $|$ \\href{{{github}}}{{GitHub}}" + r"""
\end{center}

%-----------SUMMARY-----------
\section{Professional Summary}
\small{Targeting \textbf{""" + safe_job_title + r"""} at \textbf{""" + safe_company + r"""}. """ + safe_summary + r"""}

%-----------SKILLS-----------
\section{Technical Skills}
\begin{itemize}[leftmargin=0.15in, label={}]
    \small{\item{
     \textbf{Core Competencies}{: """ + safe_skills + r"""}
    }}
\end{itemize}

%-----------EXPERIENCE-----------
\section{Work Experience}
\begin{itemize}[leftmargin=0.15in, label={}]
"""

        for exp in experience:
            exp_company = escape_latex(exp.get("company", ""))
            exp_role = escape_latex(exp.get("role", ""))
            exp_loc = escape_latex(exp.get("location", ""))
            exp_date = f"{escape_latex(exp.get('start_date', ''))} -- {escape_latex(exp.get('end_date', ''))}"
            latex += rf"""  \item
    \begin{{tabular*}}{{0.97\textwidth}}[t]{{l@{{\extracolsep{{\fill}}}}r}}
      \textbf{{{exp_role}}} & {exp_date} \\
      \textit{{{exp_company}}} & \textit{{{exp_loc}}} \\
    \end{{tabular*}}\vspace{{-5pt}}
    \begin{{itemize}}
"""
            for b in exp.get("bullets", []):
                latex += rf"      \item \small{{{escape_latex(b)}}}\n"
            latex += r"""    \end{itemize}
"""

        latex += r"""\end{itemize}

%-----------PROJECTS-----------
\section{Key Projects}
\begin{itemize}[leftmargin=0.15in, label={}]
"""
        for prj in projects:
            p_title = escape_latex(prj.get("title", ""))
            p_tags = ", ".join(escape_latex(t) for t in prj.get("tags", []))
            latex += rf"""  \item
    \textbf{{{p_title}}} $|$ \textit{{{p_tags}}}\vspace{{-4pt}}
    \begin{{itemize}}
"""
            for b in prj.get("bullets", []):
                latex += rf"      \item \small{{{escape_latex(b)}}}\n"
            latex += r"""    \end{itemize}
"""

        latex += r"""\end{itemize}

%-----------EDUCATION-----------
\section{Education}
\begin{itemize}[leftmargin=0.15in, label={}]
"""
        for edu in education:
            deg = escape_latex(edu.get("degree", ""))
            inst = escape_latex(edu.get("institution", ""))
            loc = escape_latex(edu.get("location", ""))
            yr = escape_latex(edu.get("graduation_year", ""))
            latex += rf"""  \item
    \begin{{tabular*}}{{0.97\textwidth}}[t]{{l@{{\extracolsep{{\fill}}}}r}}
      \textbf{{{inst}}} & {yr} \\
      \textit{{{deg}}} & \textit{{{loc}}} \\
    \end{{tabular*}}\vspace{{-5pt}}
"""

        latex += r"""\end{itemize}

\end{document}
"""
        return latex

    def generate_html_resume(
        self,
        job_title: str,
        company: str,
        active_skills: list[str],
        selected_projects: list[dict[str, Any]] | None = None,
        custom_summary: str | None = None,
        custom_experience: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate clean ATS-friendly HTML for direct PDF rendering with strict escaping."""
        personal = self.profile.get("personal", {})
        name = html.escape(str(personal.get("name", "Applicant")), quote=True)
        email = html.escape(str(personal.get("email", "")), quote=True)
        phone = html.escape(str(personal.get("phone", "")), quote=True)
        location = html.escape(str(personal.get("location", "")), quote=True)
        linkedin = html.escape(str(personal.get("linkedin_url", "")), quote=True)
        github = html.escape(str(personal.get("github_url", "")), quote=True)

        safe_job_title = html.escape(str(job_title), quote=True)
        safe_company = html.escape(str(company), quote=True)
        summary_text = custom_summary or self.profile.get("summary", "")
        safe_summary = html.escape(str(summary_text), quote=True)

        projects = selected_projects or self.profile.get("projects", [])[:3]
        experience = custom_experience if custom_experience is not None else self.profile.get("experience", [])
        education = self.profile.get("education", [])

        skills_html = ", ".join(f"<strong>{html.escape(str(s), quote=True)}</strong>" for s in active_skills)

        exp_html = ""
        for exp in experience:
            exp_role = html.escape(str(exp.get("role", "")), quote=True)
            exp_company = html.escape(str(exp.get("company", "")), quote=True)
            exp_loc = html.escape(str(exp.get("location", "")), quote=True)
            start_d = html.escape(str(exp.get("start_date", "")), quote=True)
            end_d = html.escape(str(exp.get("end_date", "")), quote=True)
            exp_date = f"{start_d} – {end_d}"
            bullets = "".join(f"<li>{html.escape(str(b), quote=True)}</li>" for b in exp.get("bullets", []))
            exp_html += f"""
            <div class="entry">
              <div class="row">
                <span class="role">{exp_role}</span>
                <span class="date">{exp_date}</span>
              </div>
              <div class="row sub">
                <span>{exp_company}</span>
                <span>{exp_loc}</span>
              </div>
              <ul>{bullets}</ul>
            </div>
            """

        proj_html = ""
        for p in projects:
            p_title = html.escape(str(p.get("title", "")), quote=True)
            tags = " | ".join(html.escape(str(t), quote=True) for t in p.get("tags", []))
            bullets = "".join(f"<li>{html.escape(str(b), quote=True)}</li>" for b in p.get("bullets", []))
            proj_html += f"""
            <div class="entry">
              <div class="row">
                <span class="role">{p_title}</span>
                <span class="date">{tags}</span>
              </div>
              <ul>{bullets}</ul>
            </div>
            """

        edu_html = ""
        for edu in education:
            edu_inst = html.escape(str(edu.get("institution", "")), quote=True)
            edu_yr = html.escape(str(edu.get("graduation_year", "")), quote=True)
            edu_deg = html.escape(str(edu.get("degree", "")), quote=True)
            edu_loc = html.escape(str(edu.get("location", "")), quote=True)
            edu_html += f"""
            <div class="entry">
              <div class="row">
                <span class="role">{edu_inst}</span>
                <span class="date">{edu_yr}</span>
              </div>
              <div class="row sub">
                <span>{edu_deg}</span>
                <span>{edu_loc}</span>
              </div>
            </div>
            """

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    color: #111;
    margin: 32px 40px;
    font-size: 11pt;
    line-height: 1.4;
  }}
  h1 {{
    text-align: center;
    margin: 0;
    font-size: 24pt;
    letter-spacing: 0.5px;
  }}
  .contact {{
    text-align: center;
    font-size: 9pt;
    color: #444;
    margin-top: 4px;
    margin-bottom: 18px;
  }}
  .contact a {{ color: #2563eb; text-decoration: none; }}
  h2 {{
    font-size: 11pt;
    text-transform: uppercase;
    letter-spacing: 1px;
    border-bottom: 1.5px solid #222;
    padding-bottom: 3px;
    margin-top: 14px;
    margin-bottom: 8px;
  }}
  .entry {{ margin-bottom: 10px; }}
  .row {{
    display: flex;
    justify-content: space-between;
    font-weight: 600;
  }}
  .row.sub {{
    font-weight: normal;
    font-style: italic;
    color: #444;
    font-size: 10pt;
    margin-bottom: 4px;
  }}
  ul {{
    margin: 4px 0 0 18px;
    padding: 0;
    font-size: 10pt;
  }}
  li {{ margin-bottom: 2px; }}
  .skills {{ font-size: 10pt; }}
</style>
</head>
<body>
  <h1>{name}</h1>
  <div class="contact">
    {location} • {phone} • <a href="mailto:{email}">{email}</a> • <a href="{linkedin}">LinkedIn</a> • <a href="{github}">GitHub</a>
  </div>

  <h2>Target Role</h2>
  <div class="skills">
    Applying for <strong>{safe_job_title}</strong> at <strong>{safe_company}</strong>. {safe_summary}
  </div>

  <h2>Technical Core Skills</h2>
  <div class="skills">
    {skills_html}
  </div>

  <h2>Work Experience</h2>
  {exp_html}

  <h2>Featured Projects</h2>
  {proj_html}

  <h2>Education</h2>
  {edu_html}
</body>
</html>
"""

    async def compile_to_pdf(self, html_content: str, output_path: Path) -> Path:
        """Render HTML to PDF using Playwright browser."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content(html_content, wait_until="networkidle")
            await page.pdf(
                path=str(output_path),
                format="Letter",
                print_background=True,
                margin={"top": "0.4in", "bottom": "0.4in", "left": "0.4in", "right": "0.4in"},
            )
            await browser.close()
        return output_path

    async def generate_documents(
        self,
        job_id: int,
        job_title: str,
        company: str,
        active_skills: list[str],
        selected_projects: list[dict[str, Any]] | None = None,
        job_description: str = "",
        use_ai: bool = False,
        custom_summary: str | None = None,
        custom_experience: list[dict[str, Any]] | None = None,
        custom_cover_letter: str | None = None,
    ) -> dict[str, str]:
        """
        Creates tailored .tex, .html, and compiles .pdf for a job.
        Supports Qwen2.5-3B-Instruct AI tailoring when use_ai=True.
        Returns paths to generated files, filenames, and cover letter text.
        """
        safe_company = re.sub(r"\W+", "_", company.lower()).strip("_")
        safe_title = re.sub(r"\W+", "_", job_title.lower()).strip("_")
        base_name = f"Resume_{safe_company}_{safe_title}_{job_id}"

        tex_path = _OUTPUT_DIR / f"{base_name}.tex"
        html_path = _OUTPUT_DIR / f"{base_name}.html"
        pdf_path = _OUTPUT_DIR / f"{base_name}.pdf"

        summary_to_use = custom_summary
        experience_to_use = custom_experience
        cover_letter = custom_cover_letter

        # Run Qwen2.5-3B-Instruct AI tailoring if requested
        if use_ai and job_description:
            try:
                ai_data = await self.tailor_with_ai(
                    job_title=job_title,
                    company=company,
                    job_description=job_description,
                    active_skills=active_skills,
                )
                if not summary_to_use:
                    summary_to_use = ai_data.get("summary")
                if not experience_to_use:
                    experience_to_use = ai_data.get("experience")
                if not cover_letter:
                    cover_letter = ai_data.get("cover_letter")
            except Exception as e:
                print(f"[resume_builder warning] AI tailoring fallback: {e}")

        # Default cover letter if not produced
        if not cover_letter:
            cover_letter = self.generate_cover_letter(job_title, company, active_skills)

        # Generate LaTeX
        tex_code = self.generate_latex_resume(
            job_title,
            company,
            active_skills,
            selected_projects,
            custom_summary=summary_to_use,
            custom_experience=experience_to_use,
        )
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_code)

        # Generate HTML
        html_code = self.generate_html_resume(
            job_title,
            company,
            active_skills,
            selected_projects,
            custom_summary=summary_to_use,
            custom_experience=experience_to_use,
        )
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_code)

        # Compile PDF using Playwright
        try:
            await self.compile_to_pdf(html_code, pdf_path)
        except Exception as e:
            print(f"[resume_builder error] Playwright PDF compilation: {e}")

        return {
            "base_name": base_name,
            "tex_path": str(tex_path),
            "html_path": str(html_path),
            "pdf_path": str(pdf_path) if pdf_path.exists() else str(html_path),
            "pdf_filename": pdf_path.name if pdf_path.exists() else html_path.name,
            "tex_filename": tex_path.name,
            "summary_used": summary_to_use or self.profile.get("summary", ""),
            "cover_letter": cover_letter,
        }

    def generate_cover_letter(
        self,
        job_title: str,
        company: str,
        active_skills: list[str],
    ) -> str:
        """Create a tailored cover letter (deterministic fallback)."""
        personal = self.profile.get("personal", {})
        name = personal.get("name", "Applicant")
        email = personal.get("email", "")
        phone = personal.get("phone", "")

        top_skills = ", ".join(active_skills[:5])

        return f"""Dear Hiring Team at {company},

I am writing to express my strong interest in the {job_title} position. With my background in full-stack software development and my proficiency in {top_skills}, I am confident in my ability to make an immediate positive impact on your engineering objectives.

In my recent projects, I have architected distributed high-throughput applications, optimized database query workflows, and delivered intuitive, responsive user experiences. My experience aligns closely with the technical capabilities required for the {job_title} role at {company}.

I would welcome the opportunity to discuss how my technical skills and proactive problem-solving mindset can benefit your team. Thank you for your time and consideration.

Sincerely,
{name}
{phone} | {email}
"""
