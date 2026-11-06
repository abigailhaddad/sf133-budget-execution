"""Run tieout.tie on every selected workbook for the given fiscal years; write tieout_results.csv."""
import sys, warnings
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
import pandas as pd
import tieout
warnings.filterwarnings("ignore")

def run(args):
    fy, path = args
    try:
        s, bad, j = tieout.tie(path)
        s["fiscal_year"] = fy
        s["max_abs_diff"] = float(bad["diff"].max()) if len(bad) else 0.0
        return s
    except Exception as e:
        return dict(fiscal_year=fy, file=path.split("/")[-1], error=str(e)[:100])

if __name__ == "__main__":
    years = {int(y) for y in sys.argv[1:]}
    w = pd.read_csv("workbooks.csv")
    jobs = [(int(r.fiscal_year), r.path) for r in w.itertuples() if int(r.fiscal_year) in years]
    with ProcessPoolExecutor(4, mp_context=mp.get_context("fork")) as ex:
        res = list(ex.map(run, jobs))
    pd.DataFrame(res).to_csv("tieout_results.csv", index=False)
    print("done", len(res))
