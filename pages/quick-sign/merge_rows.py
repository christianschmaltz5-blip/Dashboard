import json, sys
def merge(man):
    for pg in man:
        W,H=pg['w'],pg['h']
        text=[f for f in pg['fields'] if f['type']=='text']
        rest=[f for f in pg['fields'] if f['type']!='text']
        # group text boxes by row (y center within 7pt), merge horizontally near ones
        text.sort(key=lambda f:((f['y']+f['h']/2), f['x']))
        used=[False]*len(text); out=[]
        for i,f in enumerate(text):
            if used[i]: continue
            cy=(f['y']+f['h']/2)*H
            x0=f['x']*W; x1=(f['x']+f['w'])*W; y0=f['y']*H; y1=(f['y']+f['h'])*H
            used[i]=True
            for j in range(i+1,len(text)):
                if used[j]: continue
                g=text[j]; gcy=(g['y']+g['h']/2)*H
                if abs(gcy-cy)>7: continue
                gx0=g['x']*W; gx1=(g['x']+g['w'])*W
                if gx0 - x1 < 22:   # adjacent/overlapping on same row
                    x1=max(x1,gx1); x0=min(x0,gx0)
                    y0=min(y0,g['y']*H); y1=max(y1,(g['y']+g['h'])*H); used[j]=True
            out.append({'type':'text','kind':'box','label':'',
                        'x':round(x0/W,5),'y':round(y0/H,5),'w':round((x1-x0)/W,5),'h':round((y1-y0)/H,5)})
        pg['fields']=rest+out
    return man
for k in sys.argv[1:]:
    p=f"{k}.fields.json"; json.dump(merge(json.load(open(p))), open(p,'w'))
    print("merged", k)
