"""Install controlled Thai FDA precedent data into Local MoE Studio."""
from __future__ import annotations
import argparse, csv, json, os, shutil, tempfile, zipfile
from pathlib import Path

DEST_DEFAULT = Path(os.getenv("LOCALMOE_FDA_DATA") or (
    Path(os.getenv("LOCALAPPDATA") or (Path.home()/".localmoestudio")) /
    "LocalMoEStudio" / "thai_fda_precedent"
))
RUNTIME_FILES=["retrieval_index.csv","predecision_features.csv","cases.csv","model_config_v316.json"]
ARTIFACT_FILES=["case_order.csv","tfidf_vectorizer.joblib","tfidf_matrix.npz"]

def find(root,name):
    matches=[p for p in root.rglob(name) if p.is_file()]
    return matches[0] if matches else None

def copy_required(root,dest):
    dest.mkdir(parents=True,exist_ok=True);(dest/"artifacts").mkdir(exist_ok=True)
    for name in RUNTIME_FILES:
        src=find(root,name)
        if not src: raise FileNotFoundError(name)
        shutil.copy2(src,dest/name)
    for name in ARTIFACT_FILES:
        src=find(root,name)
        if not src: raise FileNotFoundError(name)
        shutil.copy2(src,dest/"artifacts"/name)

def sanitize(root,dest):
    ready=find(root,"precedent_decisions_sanitized.csv")
    if ready:
        shutil.copy2(ready,dest/"precedent_decisions_sanitized.csv");return
    src=find(root,"decisions_private.csv")
    if not src: raise FileNotFoundError("precedent_decisions_sanitized.csv or decisions_private.csv")
    wanted=["case_id","product_case_id","decision_status","final_class_auto_silver","label_status",
            "resolution_rationale_type_codes","resolution_decisive_factor_code","legal_acts_cited","source_sheet_link"]
    fields=["case_id","product_case_id","decision_status","final_class_auto_silver","label_status",
            "resolution_rationale_type_codes","decisive_factor_code","legal_acts_cited","source_sheet_link",
            "decision_pattern","reasoning_pattern","verification_status"]
    with src.open("r",encoding="utf-8-sig",newline="") as f, (dest/"precedent_decisions_sanitized.csv").open("w",encoding="utf-8-sig",newline="") as out:
        reader=csv.DictReader(f)
        missing=[x for x in wanted if x not in (reader.fieldnames or [])]
        if missing: raise ValueError("Missing decision columns: "+", ".join(missing))
        writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader()
        for r in reader:
            writer.writerow({"case_id":r["case_id"],"product_case_id":r["product_case_id"],
                "decision_status":r["decision_status"],"final_class_auto_silver":r["final_class_auto_silver"],
                "label_status":r["label_status"],"resolution_rationale_type_codes":r["resolution_rationale_type_codes"],
                "decisive_factor_code":r["resolution_decisive_factor_code"],"legal_acts_cited":r["legal_acts_cited"],
                "source_sheet_link":r["source_sheet_link"],"decision_pattern":"","reasoning_pattern":"",
                "verification_status":"AUTO_EXTRACTED_NOT_LEGAL_GOLD"})

def main():
    ap=argparse.ArgumentParser(description="Install Thai FDA V3.16/V3.17 controlled precedent data")
    ap.add_argument("archive");ap.add_argument("--dest",default=str(DEST_DEFAULT));args=ap.parse_args()
    archive=Path(args.archive).expanduser().resolve();dest=Path(args.dest).expanduser().resolve()
    if not archive.is_file(): raise SystemExit("Archive not found: "+str(archive))
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        with zipfile.ZipFile(archive) as z:z.extractall(root)
        if dest.exists():
            backup=dest.with_name(dest.name+".previous")
            if backup.exists():shutil.rmtree(backup)
            shutil.move(str(dest),str(backup))
        copy_required(root,dest);sanitize(root,dest)
    print(json.dumps({"installed":True,"destination":str(dest)},ensure_ascii=False,indent=2))

if __name__=="__main__":main()
