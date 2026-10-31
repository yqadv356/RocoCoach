"""Build the reviewed interview manuscript; optional dependency: python-docx.

The Markdown manuscript is the content source. Rendering and visual QA are a
separate release step; this builder alone does not certify the final layout.
"""
from pathlib import Path
import argparse
import re
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT

ROOT = Path(__file__).resolve().parents[1]


def link(paragraph, label, url):
    node = OxmlElement('w:hyperlink')
    node.set(qn('r:id'), paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True))
    run = OxmlElement('w:r')
    props = OxmlElement('w:rPr')
    color = OxmlElement('w:color'); color.set(qn('w:val'), '245C85'); props.append(color)
    run.append(props)
    text = OxmlElement('w:t'); text.text = label; run.append(text); node.append(run)
    paragraph._p.append(node)


def text(paragraph, value):
    pattern=r'(\[[^\]]+\]\([^)]+\)|https://[^\s。]+|`[^`]+`)'
    for chunk in re.split(pattern, value):
        markdown=re.fullmatch(r'\[([^\]]+)\]\(([^)]+)\)',chunk)
        if markdown:
            label,url=markdown.groups()
            if not url.startswith(('https://','http://')):
                from posixpath import normpath
                url='https://github.com/yqadv356/RocoCoach/blob/main/'+normpath('docs/'+url)
            link(paragraph,label,url)
        elif chunk.startswith('https://'):link(paragraph,chunk.removeprefix('https://'),chunk)
        elif chunk.startswith('`') and chunk.endswith('`'):paragraph.add_run(chunk[1:-1])
        else:paragraph.add_run(chunk)


def field(paragraph, instruction):
    node = OxmlElement('w:fldSimple'); node.set(qn('w:instr'), instruction)
    run = OxmlElement('w:r'); value = OxmlElement('w:t'); value.text = '1'; run.append(value)
    node.append(run); paragraph._p.append(node)


def add_table(doc, lines):
    rows = [[x.strip() for x in line.strip().strip('|').split('|')]
            for line in lines if not re.match(r'^\|[\s:|\-]+\|$', line)]
    widths = [2.2, 7.1, 7.5] if rows[0][0] == '题目角色' else [2.0, 5.6, 9.2] if rows[0][0] == '层次' else [9.2, 3.8, 3.8] if rows[0][0].startswith('相同') else [2.2, 6.0, 8.6] if rows[0][0]=='模型步骤' else [4.0, 5.5, 7.3]
    table = doc.add_table(rows=0, cols=len(rows[0]))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER; table.autofit = False
    for column, width in zip(table.columns, widths): column.width = Cm(width)
    for index, values in enumerate(rows):
        row = table.add_row()
        for col, value in enumerate(values):
            cell = row.cells[col]; cell.width = Cm(widths[col])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            props = cell._tc.get_or_add_tcPr()
            margins = OxmlElement('w:tcMar')
            for side in ['top', 'left', 'bottom', 'right']:
                item = OxmlElement('w:' + side); item.set(qn('w:w'), '85'); item.set(qn('w:type'), 'dxa'); margins.append(item)
            props.append(margins)
            borders = OxmlElement('w:tcBorders')
            bottom = OxmlElement('w:bottom'); bottom.set(qn('w:val'), 'single'); bottom.set(qn('w:sz'), '4'); bottom.set(qn('w:color'), 'D8DDE3'); borders.append(bottom); props.append(borders)
            if index == 0:
                shade = OxmlElement('w:shd'); shade.set(qn('w:fill'), 'ECEFF3'); props.append(shade)
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_before = Pt(2); paragraph.paragraph_format.space_after = Pt(3)
            paragraph.paragraph_format.line_spacing = Pt(16)
            text(paragraph,value.replace('<br>','\n'))
            for run in paragraph.runs:run.bold=index==0;run.font.size=Pt(10)
            paragraph.paragraph_format.keep_with_next=index<len(rows)-1
        rowprops = row._tr.get_or_add_trPr(); rowprops.append(OxmlElement('w:cantSplit'))
        if index == 0: rowprops.append(OxmlElement('w:tblHeader'))


def add_architecture(doc, lines):
    # Diagram labels come exclusively from the manuscript. Use native Word
    # cells rather than an external renderer, so Chinese text remains editable.
    table=doc.add_table(rows=0,cols=3);table.autofit=False
    table.alignment=WD_TABLE_ALIGNMENT.CENTER
    for col in table.columns:col.width=Cm(5.6)
    for index,line in enumerate(lines):
        values=[v.strip().replace('\\n','\n') for v in line.split('||')]
        row=table.add_row()
        cells=[row.cells[0].merge(row.cells[2])] if len(values)==1 else row.cells
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
        for cell,value in zip(cells,values):
            cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            props=cell._tc.get_or_add_tcPr()
            shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'EFF2F6' if len(values)==1 else 'F7F8FA');props.append(shade)
            margins=OxmlElement('w:tcMar')
            for side in ['top','left','bottom','right']:
                item=OxmlElement('w:'+side);item.set(qn('w:w'),'110');item.set(qn('w:type'),'dxa');margins.append(item)
            props.append(margins)
            paragraph=cell.paragraphs[0];paragraph.alignment=WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_after=Pt(4);paragraph.paragraph_format.space_before=Pt(4)
            paragraph.paragraph_format.line_spacing=Pt(16)
            paragraph.paragraph_format.keep_with_next=index<len(lines)-1
            run=paragraph.add_run(value);run.font.size=Pt(10);run.bold=index in (0,1)


def build(source, output):
    doc = Document(); sec = doc.sections[0]
    # Preserve the existing manuscript's A4 format.
    sec.page_width = Cm(21); sec.page_height = Cm(29.7)
    sec.top_margin = Cm(1.9); sec.bottom_margin = Cm(1.8)
    sec.left_margin = Cm(2.1); sec.right_margin = Cm(2.1)
    sec.header_distance = Cm(.85); sec.footer_distance = Cm(.85)
    for name, size in [('Normal', 11), ('Title', 20), ('Heading 1', 17), ('Heading 2', 12), ('Caption', 9)]:
        style = doc.styles[name]; style.font.name = 'Arial Unicode MS'
        style.font.size = Pt(size); style.font.color.rgb = RGBColor(0, 0, 0)
        style.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), 'Arial Unicode MS')
        style.paragraph_format.line_spacing = Pt({'Normal':18,'Title':28,'Heading 1':25,'Heading 2':20,'Caption':14}[name])
        style.paragraph_format.space_after = Pt(7)
        style.paragraph_format.widow_control = True
        if name=='Caption':style.font.bold=False;style.font.italic=False
        if name.startswith('Heading'):
            style.paragraph_format.space_before = Pt(9); style.paragraph_format.keep_with_next = True
    header = sec.header.paragraphs[0]
    header.paragraph_format.tab_stops.add_tab_stop(Cm(16.8), WD_TAB_ALIGNMENT.RIGHT)
    run = header.add_run('RocoCoach  洛洛\t设计与实现'); run.font.size = Pt(8)
    footer = sec.footer.paragraphs[0]; footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run('第 '); field(footer, 'PAGE'); footer.add_run(' 页  /  共 '); field(footer, 'NUMPAGES'); footer.add_run(' 页')
    for run in footer.runs: run.font.size = Pt(8)
    doc.core_properties.title = source.read_text().splitlines()[0].removeprefix('# ')
    doc.core_properties.subject = '产品流程 技术实现 难点与验证'
    doc.core_properties.author = 'RocoCoach'; doc.core_properties.last_modified_by = 'RocoCoach'
    lines = source.read_text().splitlines(); index = 0; section = 0
    while index < len(lines):
        line = lines[index]
        if line=='```architecture':
            group=[];index+=1
            while index<len(lines) and lines[index]!='```':group.append(lines[index]);index+=1
            add_architecture(doc,group)
        elif re.fullmatch(r'!\[([^\]]*)\]\(([^)]+)\)',line):
            match=re.fullmatch(r'!\[([^\]]*)\]\(([^)]+)\)',line)
            image=(source.parent/match.group(2)).resolve()
            paragraph=doc.add_paragraph();paragraph.alignment=WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.keep_with_next=True
            paragraph.paragraph_format.line_spacing=1
            paragraph.add_run().add_picture(str(image),width=Cm(16.2))
        elif line.startswith('图 '):
            doc.add_paragraph(line,'Caption')
        elif line.startswith('# '): doc.add_paragraph(line[2:].replace('——','\n——'), 'Title')
        elif line.startswith('## '):
            section += 1
            paragraph=doc.add_paragraph(line[3:], 'Heading 1')
            paragraph.paragraph_format.page_break_before=section>1
        elif line.startswith('### '): doc.add_paragraph(line[4:], 'Heading 2')
        elif line.startswith('|'):
            group = []
            while index < len(lines) and lines[index].startswith('|'):
                group.append(lines[index]); index += 1
            add_table(doc, group); continue
        elif line.strip():
            paragraph = doc.add_paragraph(); text(paragraph, line)
            if line.startswith('面试作品说明书'):
                for run in paragraph.runs: run.font.size = Pt(9)
        index += 1
    for root in [doc._element, doc.styles.element]:
        for border in list(root.iter(qn('w:pBdr'))): border.getparent().remove(border)
    output.parent.mkdir(parents=True, exist_ok=True); doc.save(output)
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'submission')
    args = parser.parse_args()
    print(build(ROOT / 'docs/SUBMISSION_DRAFT.md', args.output_dir / 'RocoCoach_设计与实现_面试稿.docx'))


if __name__ == '__main__': main()
