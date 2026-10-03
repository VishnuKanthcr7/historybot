from rag.vectorstore.retrieve import retrieve
from rag.engine.evidence import select_evidence

QUESTIONS = [
    "Who established the Moghul rule in India?",
    "Who was Babar?",
    "What was Din-e-Ilahi?",
    "What were Akbar's religious policies?",
    "Who built the Taj Mahal?",
    "What is guerilla warfare?",
    "What was Shivaji's administration?",
    "What were Shahjahan's contributions?",
    "Who was Baji Rao I?",
    "What happened after the Third Battle of Panipat?",
    "Battle of Plassey",
]


def main() -> None:
    for question in QUESTIONS:
        hits = retrieve(question, top_k=5)
        selected = select_evidence(question, question, hits)
        print(question)
        print(
            "  selected",
            [
                (
                    item.get("textbook_page_number"),
                    item.get("distance"),
                    item.get("adjusted_distance"),
                    (item.get("section") or "")[:40],
                )
                for item in selected
            ],
        )


if __name__ == "__main__":
    main()
