# 02 extract metadata

def extract_metadata(doc):
    return {
        "branch": doc.branch_name,
        "doc_type": doc.document_type_name,
        "year": doc.year,
        "section": doc.section
    }