"""Display-only extension of the documented legacy A equation; no ranking writes."""
import math
from .nar_top5_order import MODEL_VERSION, ABILITY_COEF, CORNER4_COEF, number

def reference(row, all_rows=()):
    saved=number(row.get('nar_top5_order_score'))
    if saved is not None:return dict(value=saved,kind='official',reason='保存された正式スコア')
    if row.get('nar_top5_order_version')!=MODEL_VERSION:
        return dict(value=None,kind='missing',reason='同一式を確認できないモデル、またはモデル版未取得')
    if row.get('nar_top5_order_status')!='outside_group':
        return dict(value=None,kind='missing',reason='圏外以外の未算出：'+str(row.get('nar_top5_order_status') or '状態不明'))
    for other in all_rows:
        score=number(other.get('nar_top5_order_score'))
        if score is None:continue
        pure=number(other.get('nar_top5_order_pure'));corner=number(other.get('nar_top5_order_corner4'))
        if other.get('nar_top5_order_version')!=MODEL_VERSION or pure is None or corner is None or not math.isclose(score,ABILITY_COEF*pure+CORNER4_COEF*corner,abs_tol=1e-8):
            return dict(value=None,kind='missing',reason='正式値と旧A式の尺度一致を確認できません')
    pure=number(row.get('nar_top5_order_pure'))
    if pure is None:pure=number(row.get('ver3_ability_core'))
    corner=number(row.get('nar_top5_order_corner4'))
    if corner is None:corner=number(row.get('netkeiba_corner4_rank'))
    if pure is None or corner is None or corner<1 or not corner.is_integer():
        return dict(value=None,kind='missing',reason='純能力または有効な4角想定が未取得')
    return dict(value=ABILITY_COEF*pure+CORNER4_COEF*corner,kind='reference',reason='旧Aと同一式・固定換算。正式順位・本印への反映なし',pure=pure,corner4=corner)
