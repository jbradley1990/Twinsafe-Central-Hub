import pandas as pd

def trim_csv(path="/var/opt/codesys/PlcLogic/trend_data/historical.csv", max_rows=30000):
    df = pd.read_csv(path, header=None)
    if len(df) > max_rows:
        df.tail(max_rows).to_csv(path, index=False, header=False)

if __name__ == "__main__":
    trim_csv()