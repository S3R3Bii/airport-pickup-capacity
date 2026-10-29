import argparse, json
from model import run

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["validation", "held"])
    p.add_argument("--root", default=".")
    p.add_argument("--output", default="results")
    a = p.parse_args()
    print(json.dumps(run(a.root, a.phase, a.output)))
