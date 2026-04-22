def format_results(results):

    output = []

    for r in results:
        output.append({
            "text": r.content,
            "score": r.score,
            "doc_id": r.doc_id,
            "page": r.page_number,
            "heading": r.heading,
            "file": r.file_name,
            "branch": r.branch,
            "type": r.doc_type,
        })

    return output