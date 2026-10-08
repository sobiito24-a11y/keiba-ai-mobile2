"""Read-only explanation of saved marks. No ticket or purchase-navigation calls."""
from .race_insight_common import (facts, describe, label, leading_features, position_sentence,
                                  VERSION, GAP_CALIBRATION)


def overview(horses, pace):
    leaders = [label(h) for h in horses if h['style'] == '逃']
    forward = [label(h) for h in horses if h['group'] == 'front']
    line = pace + 'ペース想定。' if pace in ('S', 'M', 'H') else '予測ペースは未取得。'
    if leaders:
        line += '逃げ候補は' + '、'.join(leaders[:3]) + ('など。' if len(leaders) > 3 else '。')
    if forward:
        line += '前方で運ぶ想定は' + '、'.join(forward[:4]) + ('など。' if len(forward) > 4 else '。')
    line += {'H': '前で競り合えば消耗が進む流れ。後ろの馬も、脚質と能力の裏付けがあってこそ差す余地が生まれる。',
             'S': '前で脚を残せる形が考えられるが、位置だけで決まらず、後方勢の能力と仕掛けも焦点。',
             'M': '極端な前後の有利を置かず、道中のロスと仕掛けのタイミングを比べたい。'}.get(pace, '脚質だけからペースや差し有利を補わず、取得済みの位置情報までで考える。')
    return line


def overall(centers, opponents, extra, mode):
    if not centers:
        return ['保存された正式候補と印から中心を特定できない。欠損した評価を補わず、全体の比較は保留とする。']
    lead = centers[0]
    line = '中心の' + label(lead) + 'は'
    if mode == 'jra' and lead['formal_rank'] is not None:
        line += f"正式{int(lead['formal_rank'])}位。"
    elif lead['pure_rank'] is not None:
        line += f"純能力{int(lead['pure_rank'])}位。"
    else:
        line += '保存された印を起点に見る。'
    if lead['conditions']:
        line += lead['conditions'][0] + 'が比較材料で、'
    line += position_sentence(lead)
    if mode == 'jra':
        if lead['training'] in ('C', 'D'):
            line += '調教面の懸念もあり、展開だけで安心はできない。'
        elif lead['training'] in ('A', 'B') and lead['rest_days'] is not None:
            line += f"調教{lead['training']}は確認材料だが、前走から{lead['rest_days']:g}日の間隔も併せて見たい。"
    paragraphs = [line]
    # Highlight distinctive facts among ALREADY selected formal horses only.
    # This affects prose emphasis, not roles, ranks, marks, or selection order.
    peers = centers[1:] + [h for h in opponents if h['member']]
    prominent = next((h for h in sorted(peers, key=lambda h: -len(leading_features(h)))
                      if leading_features(h)), None)
    if prominent:
        features = leading_features(prominent)
        text = label(prominent) + ('は最終' + f"{int(prominent['formal_rank'])}位ながら、" if prominent['formal_rank'] is not None else 'は')
        text += '・'.join(features) + ('がいずれも1位。' if len(features) > 1 else 'が1位。')
        if prominent['pure'] is not None and lead['pure'] is not None:
            delta = prominent['pure'] - lead['pure']
            if delta > 0:
                text += '純能力では中心を' + f'{delta:.2f}' + '上回り、印の強さと能力面の強みは分けて見たい。'
        text += position_sentence(prominent)
        if mode == 'jra' and prominent['training'] in ('C', 'D'):
            text += '調教面も慎重な確認が必要。'
        if prominent['weight_change'] is not None and prominent['weight_change'] > 0:
            text += f"斤量も前走比+{prominent['weight_change']:g}kg。"
        text += 'これらの特徴から最終印の決定理由までは断定しない。'
        paragraphs.append(text)
    alternatives = [h for h in opponents if h['member'] and h is not prominent and h['pace_effect'] == 'plus']
    if alternatives:
        h = alternatives[0]
        text = '一方、' + label(h)
        text += ('は前が残る形で持ち味を生かす相手。' if h['pace'] == 'S' else 'は前受け組が消耗する形で浮上する相手。')
        if h['pure'] is not None and lead['pure'] is not None and h['pure'] < lead['pure']:
            text += f"中心との純能力差は{lead['pure']-h['pure']:.2f}あり、展開の助けなしでも互角とは言い切れない。"
        paragraphs.append(text)
    if extra:
        text = '追加の' + '・'.join(label(h) for h in extra) + 'は、本文に挙げた条件が揃う場合の注意対象。'
        if any(not h['close_gap'] for h in extra):
            text += '能力差の大きい馬も含むため、位置取り変化だけで上位と同等には扱わない。'
        paragraphs.append(text)
    if lead['pace'] == 'H':
        paragraphs.append('先行勢がどこまで消耗するかが分岐点。前で粘る力と、後ろから差を詰める力を区別して考えたい。')
    elif lead['pace'] == 'S':
        paragraphs.append('前が脚を残す形を重く見るか、後方勢が能力で追い上げる形を重く見るかが比較の分かれ目になる。')
    elif lead['pace'] == 'M':
        paragraphs.append('一律の展開有利は置かず、前で運ぶ馬の残り目と後方勢の追い上げを比較したい。')
    else:
        paragraphs.append('ペース情報がないため、展開の後押しを前提に評価を決め切らない。')
    return paragraphs


def opponent_groups(opponents, paragraphs):
    """Partition existing prose by resolved formal membership, never rank or mark."""
    groups = []
    for member, title in [(True, '相手本線（正式Top5）'),
                          (False, 'その他の印付き馬（参考）')]:
        selected = [(h, paragraph) for h, paragraph in zip(opponents, paragraphs)
                    if h['member'] == member]
        if selected:
            groups.append(dict(title=title, horse_numbers=[h['no'] for h, _ in selected],
                               paragraphs=[paragraph for _, paragraph in selected]))
    return groups


def generate(result, rows, development):
    mode = result.race_mode
    horses = facts(result, rows, development)
    if mode == 'jra':
        from .jra_race_insight import select
    else:
        from .nar_race_insight import select
    centers, opponents, extra = select(horses)
    anchor = centers[0] if centers else None
    audit = {}
    for role, selected in [('center', centers), ('opponent', opponents), ('additional', extra)]:
        for h in selected:
            reasons = ['existing_final_mark'] if role != 'additional' else []
            if role == 'additional':
                if mode == 'nar':
                    from .nar_race_insight import additional_routes
                    reasons = additional_routes(h)
                else:
                    reasons = ['close_gap_condition_pace']
            audit[h['no']] = dict(role=role, route=reasons, positive=h['conditions'],
                                  risks=h['risks'], ability_gap=h['gap_to_group'])
    sections = [
        dict(title='展開予想', paragraphs=[overview(horses, development['pace_prediction'])]),
        dict(title='中心候補', paragraphs=[describe(h, mode, 'center', centers[1] if h is anchor and len(centers)>1 else anchor) for h in centers]
             or ['正式候補の印が未取得のため、中心候補は保留。']),
        dict(title='相手本線', paragraphs=[describe(h, mode, 'opponent', anchor) for h in opponents]
             or ['該当する印の馬は確認できません。']),
        dict(title='追加注目馬', paragraphs=[describe(h, mode, 'additional', anchor) for h in extra]
             or ['該当なし。']),
        dict(title='総合考察', paragraphs=overall(centers, opponents, extra, mode)),
    ]
    sections[2]['groups'] = opponent_groups(opponents, sections[2]['paragraphs'])
    return dict(version=VERSION, mode=mode, policy=mode+'_marked_explanation',
                gap_calibration=GAP_CALIBRATION, centers=[h['no'] for h in centers],
                opponents=[h['no'] for h in opponents], additional=[h['no'] for h in extra],
                horses=horses, selection_audit=audit, sections=sections)
