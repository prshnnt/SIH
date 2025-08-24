import pandas as pd
import chromadb
from sentence_transformers import SentenceTransformer
import os

import shutil
if os.path.exists("chroma_db"):
    shutil.rmtree("chroma_db")

# Read Excel file
df = pd.read_excel("./data/sih_ps_2024_cleaned.xlsx", sheet_name="sih_ps", engine="openpyxl")

client = chromadb.PersistentClient(path="chroma_db")
collection = client.create_collection("sih_ps")


model = SentenceTransformer("all-MiniLM-L6-v2")

new_data_dict = {}

new_data_dict = {
    row.Statement_id: f"Title: {row.Title}.\nTechnology_Bucket: {row.Technology_Bucket}.\nDepartment: {row.Department}.\nOrganisation: {row.Organisation}.\nDescription: {row.Description}"
    for row in df.itertuples(index=False)
}

embeddings = model.encode(list(new_data_dict.values()), show_progress_bar=True)


collection.add(
    ids=list(new_data_dict.keys()),
    embeddings=embeddings.tolist()
)