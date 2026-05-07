import pandas as pd
import os

csv_folder = '/home/flask/data/dj30/csv/'

file_list = os.listdir(csv_folder)
for f in file_list:
    print(f)
    df=pd.read_csv(csv_folder + f)
    df = df[:-2]
    df.to_csv(csv_folder + f,index=False)