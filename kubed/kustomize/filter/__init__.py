from kubed.krm import common as c

def transform(krm: dict) -> dict:
  t = krm["functionConfig"]["target"]
  krm["items"] = [r for r in krm["items"] if c.targeted(r, t)]
  return krm