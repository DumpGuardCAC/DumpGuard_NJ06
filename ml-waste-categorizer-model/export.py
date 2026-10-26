import os, sys, subprocess, shutil
os.environ["KERAS_BACKEND"] = "tensorflow"
from model import build_model

W, OUTDIR = sys.argv[1], sys.argv[2]
IMG = int(os.environ.get("DG_IMG", 224))
model, _ = build_model(IMG, weights=None)
model.load_weights(W)
sm = OUTDIR + "_savedmodel"
shutil.rmtree(sm, ignore_errors=True)
model.export(sm)
shutil.rmtree(OUTDIR, ignore_errors=True)
exe = os.path.join(os.path.dirname(sys.executable), "tensorflowjs_converter.exe")
subprocess.check_call([exe, "--input_format=tf_saved_model", "--output_format=tfjs_graph_model",
                        "--quantize_float16=*", sm, OUTDIR])
print("tfjs size MB:", sum(os.path.getsize(os.path.join(OUTDIR, f)) for f in os.listdir(OUTDIR)) / 1e6)
