"""Frozen display scale; never used for ranking, marks, or prediction math."""
import math
VERSION='nar_display_z_v1_20261020'
# Unique race/model/runner observations, existing 10/17-18 files only; no outcomes.
# Legacy statistics cover scored Top5 only, not an all-runner ability distribution.
BASELINES={
 'nar_top5_corner_order_v1_20261006':dict(mean=-0.5462647149767442,sd=0.671560996013084,n=215,races=43),
 'nar_f2_actual_course_v1_20261020':dict(mean=24.628733738612528,sd=21.91666461398439,n=627,races=61),
}

def project(value,model,status='',member=None):
 try:
  raw=float(value)
  if isinstance(value,bool) or not math.isfinite(raw):raw=None
 except (ValueError,TypeError):raw=None
 state='available' if raw is not None else 'error' if any(k in str(status) for k in ('error','invalid')) else 'not_calculated' if status=='outside_group' else 'missing'
 b=BASELINES.get(model)
 scaled=50+10*(raw-b['mean'])/b['sd'] if raw is not None and b else None
 return dict(version=VERSION,model=model,raw=raw,value=scaled,status=state,top5=member,
  baseline=b,method='50 + 10 × (内部値 − 固定平均) / 固定標準偏差。クリップなし。JRAと別尺度・勝率ではありません。' if b else '未対応モデル：内部値を表示')
