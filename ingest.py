from langchain_core.documents import Document
import pandas as pd

df = pd.read_excel("data/financialdata.xlsx")

documents = []

for _, row in df.iterrows():

    text = f"""
    Company: {row['shortName']}
    Industry: {row['industry']}
    EBITDA Margin: {row['ebitdaMargins']}
    Profit Margin: {row['profitMargins']}
    Gross Margin: {row['grossMargins']}
    Operating Cashflow: {row['operatingCashflow']}
    """

    documents.append(
        Document(
            page_content=text,
            metadata={
                "department": "finance"
            }
        )
    )

print(documents[0])