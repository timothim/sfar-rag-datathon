"""Apply the V3.1 overlay errata (p. 81, p. 87, p. 113) copied from the official PDF to the file given as argv[1]."""
import sys
F = sys.argv[1]
s = open(F, encoding='utf-8').read()
old81 = '''</ul>
</li>
<br/>
<li>○ Patients à faible risque : aucun des critères ci-dessus</li>
</ul>
</td>
<td>
          Céfazoline<br/><br/>
<u>Alternative :</u><br/>
          Céfuroxime
        </td>
<td>
          2g IVL<br/><br/>
          1,5g IVL
        </td>
<td>
          1g si durée &gt; 4h, puis toutes les 4h jusqu'à fin de chirurgie<br/><br/>
          0,75g si durée &gt;2h puis toutes les 2h jusqu'à fin de chirurgie
        </td>
<td>
          ●●● (Avis d'experts)<br/><br/>
          ●●● (GRADE 2)
        </td>
</tr>
'''
new81 = '''</ul>
</li>
</ul>
</td>
<td>
          Céfazoline<br/><br/>
<u>Alternative :</u><br/>
          Céfuroxime
        </td>
<td>
          2g IVL<br/><br/>
          1,5g IVL
        </td>
<td>
          1g si durée &gt; 4h, puis toutes les 4h jusqu'à fin de chirurgie<br/><br/>
          0,75g si durée &gt;2h puis toutes les 2h jusqu'à fin de chirurgie
        </td>
<td>
          ●●● (Avis d'experts)
        </td>
</tr>
<tr>
<td>
<ul style="list-style-type: none; padding-left: 0;">
<li>▪ Cholécystectomie élective par laparoscopie
              <ul style="list-style-type: none; padding-left: 20px;">
<li>○ Patients à faible risque : aucun des critères ci-dessus</li>
</ul>
</li>
</ul>
</td>
<td colspan="3">PAS D'ANTIBIOPROPHYLAXIE</td>
<td>◉◉◎ (GRADE 2)</td>
</tr>
'''
old113 = '''<li>○ Patients à faible risque : <i>aucun des critères ci-dessus</i></li>
</ul>
</td>
<td>Céfazoline</td>
<td>30 mg/kg IVL</td>
<td>30 mg/kg si durée &gt; 4h puis toutes les 4h jusqu'à fin de chirurgie</td>
<td>●●● (Avis d'experts)</td>
</tr>
<tr>
<td></td>
<td colspan="3">PAS D'ANTIBIOPROPHYLAXIE</td>'''
new113 = '''</ul>
</td>
<td>Céfazoline</td>
<td>30 mg/kg IVL</td>
<td>30 mg/kg si durée &gt; 4h puis toutes les 4h jusqu'à fin de chirurgie</td>
<td>●●● (Avis d'experts)</td>
</tr>
<tr>
<td>▪ Cholécystectomie élective par laparoscopie
<ul>
<li>○ Patients à faible risque : <i>aucun des critères ci-dessus</i></li>
</ul>
</td>
<td colspan="3">PAS D'ANTIBIOPROPHYLAXIE</td>'''
old87 = "Si céfotaxime : **gentamicine 6 à 7 mg/kg IVL + métronidazole 1g IVL**"
new87 = "Si céfoxitine : **gentamicine 6 à 7 mg/kg IVL + métronidazole 1g IVL**"
for o, n in ((old81, new81), (old113, new113), (old87, new87)):
    assert s.count(o) == 1, o[:60]
    s = s.replace(o, n)
open(F, 'w', encoding='utf-8').write(s)
print("ok")
