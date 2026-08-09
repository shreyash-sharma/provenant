from importlib.resources import files


def test_generation_templates_are_packaged() -> None:
    template = files("provenant.core.generation.templates").joinpath("claude_md.j2")

    assert template.is_file()


def test_tree_sitter_queries_are_packaged() -> None:
    query = files("provenant.core.ingestion.queries").joinpath("java.scm")

    assert query.is_file()
