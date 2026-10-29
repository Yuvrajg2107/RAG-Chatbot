"""Build the fictional, redistributable PDF corpus used by the demo and evaluation."""

import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parent.parent
CORPUS = {
    "student-handbook.pdf": [
        (
            "Enrollment & attendance",
            [
                "Northstar Learning Institute | Fictional demonstration handbook | 2026 edition.",
                "The Applied AI certificate lasts 12 weeks. Teaching begins on 3 August 2026. Classes meet on Mondays and Wednesdays from 6:00 PM to 8:00 PM.",
                "Students must attend at least 80 percent of scheduled classes to qualify for the certificate. Absences should be reported to the program coordinator by email before the session.",
                "Enrollment closes on 24 July 2026. Applicants must complete the Python foundations module before enrollment. The cohort is limited to 30 students.",
            ],
        ),
        (
            "Assessment & extensions",
            [
                "Assessment consists of weekly assignments worth 40 percent, a capstone project worth 50 percent, and participation worth 10 percent of the final grade.",
                "Students need a final grade of at least 60 percent to pass. Weekly assignments are due every Sunday at 11:59 PM in the institute's local time.",
                "A late assignment loses 5 percentage points per day and is not accepted after 3 days. An extension must be requested at least 48 hours before the deadline. Approved medical absences are exempt from the late penalty.",
            ],
        ),
        (
            "Capstone & academic integrity",
            [
                "The capstone submission deadline is 23 October 2026 at 5:00 PM. Teams may contain between one and three students.",
                "Every capstone submission must include a source-code repository, a README with setup instructions, an evaluation report, and a demonstration video no longer than 5 minutes.",
                "Students may use AI tools but must disclose their use in the README. All external datasets and code must be attributed. Fabricated evaluation results are prohibited.",
                "The final presentation is 10 minutes long, followed by 5 minutes of questions. Projects are assessed on correctness, evidence quality, usability, and the team's explanation of limitations.",
            ],
        ),
    ],
    "research-lab-policy.pdf": [
        (
            "Lab access & safety",
            [
                "Northstar Research Lab | Fictional demonstration policy | Version 1.2.",
                "The research lab opens Monday through Friday from 9:00 AM to 7:00 PM. Weekend access requires written approval from the lab manager.",
                "Before entering the lab, students must complete the safety orientation and register their institute ID card. Visitors must be accompanied by a registered lab member.",
                "Food and open drinks are not permitted near workstations. Report equipment faults to the lab manager; do not attempt electrical repairs. The emergency assembly point is the east courtyard.",
            ],
        ),
        (
            "Compute resources",
            [
                "Each student receives a monthly compute budget of 20 GPU hours. Unused GPU hours do not roll over to the next month.",
                "GPU sessions have a maximum duration of 4 hours. Jobs still running at the end of a session are terminated automatically, so save checkpoints to persistent storage.",
                "Reserve a GPU workstation through the lab booking portal at least 24 hours before use. Cancel a reservation at least 2 hours in advance to avoid a booking warning.",
                "Cryptocurrency mining and hosting public services on lab machines are prohibited. Software that needs administrator access must be installed by lab staff.",
            ],
        ),
        (
            "Research data",
            [
                "Student research datasets must be stored in the institute-managed project drive. Personal information must be removed or anonymized before it is uploaded.",
                "Confidential research data must not be sent to external AI APIs without written authorization from the data owner. Use synthetic data for public demonstrations.",
                "Project data is retained for 90 days after project completion and then deleted. A retention extension requires approval from the research supervisor before the deletion date.",
                "Report a suspected data exposure to the lab manager within 24 hours. Public datasets must retain their original license and attribution information.",
            ],
        ),
    ],
    "library-guide.pdf": [
        (
            "Library hours & borrowing",
            [
                "Northstar Library | Fictional demonstration guide | 2026 edition.",
                "The library is open Monday through Saturday from 8:00 AM to 9:00 PM. It is closed on Sundays and institute holidays.",
                "Students may borrow up to 5 books at a time. The standard loan period is 14 days. A book can be renewed once for another 14 days if no other reader has reserved it.",
                "Overdue books incur a charge of 2 credits per book per day. Borrowing privileges are paused when unpaid charges reach 20 credits. Lost books must be replaced or paid for at the listed replacement value.",
            ],
        ),
        (
            "Study rooms & accessibility",
            [
                "Group study rooms can be booked for up to 2 hours per day. Each room accommodates up to 6 people. Bookings are made through the library portal.",
                "A booking is released if no one arrives within 15 minutes of the scheduled start. Quiet study desks are available without a reservation on the second floor.",
                "Accessible workstations with screen readers are on the ground floor. Students can request accessible copies of course readings from the library help desk. Requests normally take 3 working days.",
            ],
        ),
        (
            "Digital resources & help",
            [
                "Off-campus access to digital journals requires an institute account and multi-factor authentication. Sign in through the library portal before opening a journal link.",
                "The library offers a research-skills workshop every Thursday at 4:00 PM. Workshops cover literature search, citation management, and identifying reliable sources.",
                "Research consultations can be booked by emailing library-help@example.org. The help desk responds within 2 working days. This address is fictional and must not be used for actual requests.",
                "Interlibrary loan requests are limited to 3 active requests per student. Delivery times depend on the lending institution and are not guaranteed.",
            ],
        ),
    ],
}

# Development fixture, not a held-out benchmark or a claim about real institute policies.
QUESTIONS = [
    ("How long is the Applied AI certificate?", "student-handbook.pdf", 1, "12 weeks"),
    (
        "What attendance is needed to qualify for the certificate?",
        "student-handbook.pdf",
        1,
        "80 percent",
    ),
    ("When does enrollment close?", "student-handbook.pdf", 1, "24 July 2026"),
    ("How much of the final grade is the capstone worth?", "student-handbook.pdf", 2, "50 percent"),
    ("What is the minimum passing grade?", "student-handbook.pdf", 2, "60 percent"),
    ("When must an assignment extension be requested?", "student-handbook.pdf", 2, "48 hours"),
    ("When is the capstone submission deadline?", "student-handbook.pdf", 3, "23 October 2026"),
    ("How many students can be on a capstone team?", "student-handbook.pdf", 3, "three students"),
    ("How long can the capstone demonstration video be?", "student-handbook.pdf", 3, "5 minutes"),
    (
        "What are the research lab opening hours?",
        "research-lab-policy.pdf",
        1,
        "9:00 AM to 7:00 PM",
    ),
    ("Where is the lab emergency assembly point?", "research-lab-policy.pdf", 1, "east courtyard"),
    (
        "How many GPU hours does each student get monthly?",
        "research-lab-policy.pdf",
        2,
        "20 GPU hours",
    ),
    ("What is the maximum duration of a GPU session?", "research-lab-policy.pdf", 2, "4 hours"),
    ("How long is project research data retained?", "research-lab-policy.pdf", 3, "90 days"),
    (
        "Can confidential research data be sent to external AI APIs?",
        "research-lab-policy.pdf",
        3,
        "written authorization",
    ),
    ("How many library books can a student borrow?", "library-guide.pdf", 1, "5 books"),
    ("How long can a group study room be booked per day?", "library-guide.pdf", 2, "2 hours"),
    (
        "What is required to access digital journals off campus?",
        "library-guide.pdf",
        3,
        "multi-factor authentication",
    ),
    ("What is the cafeteria menu for next Tuesday?", None, None, None),
    ("Who won the football world cup in 2018?", None, None, None),
    ("What is the campus parking permit price?", None, None, None),
    ("What brand of GPU does the research lab use?", None, None, None),
    ("What is the librarian's personal phone number?", None, None, None),
    ("What scholarship amount is available for the certificate?", None, None, None),
]


def create_samples():
    directory = ROOT / "samples"
    directory.mkdir(exist_ok=True)
    styles = getSampleStyleSheet()
    styles["Title"].textColor = colors.HexColor("#24574b")
    styles["BodyText"].fontSize = 11
    styles["BodyText"].leading = 18
    for filename, pages in CORPUS.items():
        flow = []
        for index, (title, paragraphs) in enumerate(pages, 1):
            if index > 1:
                flow.append(PageBreak())
            flow.extend(
                [
                    Paragraph("NORTHSTAR / DEMO DOCUMENT", styles["Heading3"]),
                    Spacer(1, 0.25 * inch),
                    Paragraph(escape(title), styles["Title"]),
                    Spacer(1, 0.2 * inch),
                ]
            )
            for text in paragraphs:
                flow.extend([Paragraph(escape(text), styles["BodyText"]), Spacer(1, 0.15 * inch)])
            flow.extend(
                [
                    Spacer(1, 0.3 * inch),
                    Paragraph(
                        f"Fictional sample · Page {index} · Not an official policy",
                        styles["Italic"],
                    ),
                ]
            )
        SimpleDocTemplate(
            str(directory / filename),
            title=filename.removesuffix(".pdf").replace("-", " ").title(),
            author="Margin demo corpus",
            pageCompression=1,
        ).build(flow)
    questions = [
        {
            "id": f"q{i:02}",
            "question": q,
            "answerable": filename is not None,
            "expected_file": filename,
            "expected_page": page,
            "expected_phrase": phrase,
        }
        for i, (q, filename, page, phrase) in enumerate(QUESTIONS, 1)
    ]
    (ROOT / "evaluation").mkdir(exist_ok=True)
    (ROOT / "evaluation" / "questions.json").write_text(
        json.dumps(questions, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Created {len(CORPUS)} sample PDFs and {len(questions)} evaluation questions.")


if __name__ == "__main__":
    create_samples()
