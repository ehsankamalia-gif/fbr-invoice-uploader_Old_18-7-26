import pandas as pd

def parse_recipients(file_path: str):
    df = pd.read_excel(file_path)
    return df.to_dict('records'), df.columns.tolist()
