import argparse


def main():
    parser = argparse.ArgumentParser(description="K8s RAG Assistant")
    parser.add_argument(
        "mode",
        choices=["ingest", "serve", "eval"],
        help="ingest=scrape docs, serve=start API, eval=run evaluation queries"
    )
    args = parser.parse_args()

    if args.mode == "ingest":
        from services.ingestion.ingest import run
        run()

    elif args.mode == "serve":
        import uvicorn
        uvicorn.run(
            "services.query_api.app:app",
            host="0.0.0.0",
            port=8000,
            reload=True
        )

    elif args.mode == "eval":
        from evaluation.queries import run_eval
        run_eval()


if __name__ == "__main__":
    main()