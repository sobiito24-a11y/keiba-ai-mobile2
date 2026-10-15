"""Conservative ruled-table OCR. Columns are identified by printed headers."""
import subprocess
import time
from pathlib import Path
import tempfile
import numpy as np
from PIL import Image, ImageOps


def read_grid(image, binary):
    started = time.monotonic()
    pixels = np.asarray(image).astype(int)
    gray_lines = ((pixels.max(2)-pixels.min(2)<12)
                  & (pixels.mean(2)>180) & (pixels.mean(2)<225))

    def centers(values):
        groups=[]
        for value in values:
            if not groups or value-groups[-1][-1]>2: groups.append([])
            groups[-1].append(int(value))
        return [round(sum(g)/len(g)) for g in groups]

    ys=centers(np.flatnonzero(gray_lines.mean(1)>.85))
    with tempfile.TemporaryDirectory(prefix='keiba_cells_') as directory:
        def read(box, language='jpn', psm=7, numeric=False, scale=1):
            if time.monotonic()-started>120:
                raise ValueError('セルOCRが120秒に達しました。確認表で修正してください。')
            cell=image.crop(box)
            # Separate coloured text / white frame digits from the cell background.
            if psm!=6:
                a=np.asarray(cell).astype(int)
                background=np.median(a.reshape(-1,3),axis=0)
                ink=np.max(np.abs(a-background),axis=2)>60
                cell=Image.fromarray(np.where(ink,0,255).astype('uint8'))
            cell=ImageOps.expand(cell.resize((cell.width*scale,cell.height*scale)),border=12,fill='white')
            path=Path(directory)/'cell.png';cell.save(path)
            cmd=[binary,str(path),'stdout','-l',language,'--psm',str(psm)]
            if numeric: cmd+=['-c','tessedit_char_whitelist=0123456789.-~']
            result=subprocess.run(cmd,capture_output=True,timeout=10)
            if result.returncode: return ''
            return ''.join(result.stdout.decode('utf-8',errors='replace').split())

        for top,bottom in zip(ys,ys[1:]):
            if bottom-top<25 or bottom-top>image.height*.12: continue
            xs=centers(np.flatnonzero(gray_lines[top+3:bottom-2].mean(0)>.8))
            if len(xs)<4: continue
            edges=[0]+xs
            if image.width-1-edges[-1]>5: edges.append(image.width-1)
            headers={}
            for left,right in zip(edges,edges[1:]):
                if right-left<15: continue
                text=read((left+2,top+3,right-2,bottom-2),psm=6,scale=3)
                for label in ('馬番','馬名','単勝','複勝'):
                    if label in text: headers[label]=(left,right)
            if len(headers)!=4: continue
            rows=[]; row_height=None
            for y1,y2 in zip(ys,ys[1:]):
                if y1<bottom: continue
                if y2-y1>bottom-top*.85 or y2-y1<15: break
                if row_height is not None and abs((y2-y1)-row_height)>row_height*.25: break
                row_height=y2-y1
                row={'_box':[0,y1,image.width,y2],'_cells':{}}
                for label,(left,right) in headers.items():
                    box=(left+2,y1+3,right-2,y2-2)
                    language='jpn' if label=='馬名' else 'eng'
                    # Compare actual readings at different resolutions. An exact
                    # two-reading agreement is a draft, never an automatic commit.
                    row[label]=read(box,language=language,numeric=label!='馬名',
                                    scale=2)
                    alternative=read(box,language=language,numeric=label!='馬名',scale=3)
                    readings=[row[label],alternative]
                    if row[label]!=alternative:
                        third=read(box,language=language,numeric=label!='馬名',scale=1)
                        readings.append(third)
                        if third==alternative: row[label]=third
                    row['_cells'][label]={'box':list(box),'primary':row[label],
                                          'alternative':alternative,'readings':readings,
                                          'disagreement':len(set(readings))>1}
                rows.append(row)
            return rows,round(time.monotonic()-started,3)
    return [],round(time.monotonic()-started,3)
