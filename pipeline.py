import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import fhrs

    from sci_dataset_list import builders

    return builders, fhrs


@app.cell
def _(fhrs):
    dataset = fhrs.load("sci_dataset_list", manage=True)
    return (dataset,)


@app.cell
def _(builders, dataset):
    builders.build_rss(dataset.resource("rss"))
    return


@app.cell
def _(builders, dataset):
    builders.build_rss_catalog(dataset.resource("rss_catalog"))
    return


@app.cell
def _(builders, dataset):
    builders.build_dataset_pages(dataset.resource("dataset_pages"))
    return


@app.cell
def _(builders, dataset):
    builders.build_page_metadata(dataset.resource("page_metadata"))
    return


@app.cell
def _(builders, dataset):
    builders.build_datasets(dataset.resource("datasets"))
    return


@app.cell
def _(builders, dataset):
    builders.build_references(dataset.resource("references"))
    return


if __name__ == "__main__":
    app.run()
