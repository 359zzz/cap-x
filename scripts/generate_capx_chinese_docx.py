# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


OUTPUT_PATH = Path(__file__).resolve().parents[1] / "capx_openarm_pure_chinese.docx"

TITLE = "capx 项目介绍与技术路线说明"
INTRO = (
    "本文档以正式项目方案说明的方式，对 capx 的整体定位、建设目标、系统架构、真实机器人方向、"
    "关键技术路线、能力体系与后续应用前景进行结构化介绍。整体表达强调项目建设思路、功能体系和工程化价值，"
    "不采用操作手册写法，也不围绕具体代码细节展开。"
)

SECTIONS: list[tuple[str, list[str]]] = [
    (
        "1. capx 项目总体定位",
        [
            "（1）项目目标：capx 是一个面向机器人操作任务的统一型系统平台，目标是将大模型推理能力、机器人环境管理能力、视觉与触觉等感知能力、动作执行能力、任务调度能力以及评测训练能力整合到同一项目框架之中，形成一套可扩展、可评估、可持续演化的机器人智能体基础平台。",
            "（2）项目定位：该项目并不局限于单一功能实现，而是强调从任务输入、环境感知、动作调用、状态反馈到任务闭环的完整系统建设。其定位更接近一个机器人智能体运行平台，而不仅仅是机械臂控制程序或模型调用外壳。",
            "（3）项目意义：通过构建统一框架，capx 可以降低不同模块之间的耦合程度，使机器人能力不再依赖大量临时脚本和手工拼接流程，从而为后续的功能扩展、模型替换、真实部署和系统评测打下基础。"
        ],
    ),
    (
        "2. capx 项目拟解决的关键问题",
        [
            "（1）解决能力分散问题：传统机器人项目往往存在控制、感知、界面、任务逻辑彼此分离的问题，导致每增加一个任务都需要重新组合模块，开发效率低，后期维护成本高。capx 的目标是把这些能力统一封装到同一框架中。",
            "（2）解决任务流程割裂问题：很多系统只能完成局部动作，却缺乏从任务输入到任务完成的完整闭环。capx 试图建立完整的任务执行链路，使智能体能够在统一环境中接收任务、调用工具、获取反馈并持续调整行为。",
            "（3）解决真实与仿真脱节问题：仅有仿真能力无法支撑真实部署，仅有真实控制能力也难以形成系统性评测。capx 通过统一架构，让仿真任务与真实机器人路径在理念和接口上尽量保持一致，为后续从研究走向落地提供条件。",
            "（4）解决能力沉淀不足问题：项目希望将动作语义、感知接口、任务模板、服务接入方式与评测流程沉淀为长期可复用资产，而不是每完成一个需求就留下一个不可复用的孤立实现。"
        ],
    ),
    (
        "3. capx 项目总体架构设计",
        [
            "（1）环境层：负责承载具体任务环境与状态反馈，包括仿真环境与真实机器人环境两大方向。该层提供智能体所需的任务上下文、观测信息与执行结果，是整个系统的运行基础。",
            "（2）集成层：负责接入机器人驱动、感知服务、执行接口和其他硬件或中间件能力。该层强调能力封装与接口统一，尽可能减少底层差异对上层任务逻辑的影响。",
            "（3）任务执行层：负责将自然语言目标或高层任务转化为可执行的动作序列、组合逻辑和反馈驱动流程。该层是感知与控制协同工作的核心区域，也是形成任务闭环的关键环节。",
            "（4）服务层：负责网页界面、任务中继、外部系统接入、状态查询以及模型服务连接等功能，使项目不仅能在本地运行，还能承接更上层的交互与系统调用。",
            "（5）评测训练层：负责 benchmark、实验对比、训练反馈和性能提升工作，使 capx 不只是一个能跑的系统，更是一个能比较、能优化、能持续提升的项目平台。"
        ],
    ),
    (
        "4. capx 项目的核心特征",
        [
            "（1）统一性：项目将感知、控制、环境、任务执行、界面、接入与评测纳入同一工程体系之中，使不同能力不再孤立存在。",
            "（2）模块化：系统在设计上强调分层和接口边界，便于后续替换感知模型、替换机器人底座、调整任务逻辑或增加新的交互方式。",
            "（3）闭环性：项目强调基于反馈的任务执行逻辑，而不是单纯预定义动作序列。视觉、触觉、状态信息可以在任务执行中持续参与决策修正。",
            "（4）可扩展性：capx 既可承接仿真评测，也可承接真实机器人路径，还能够连接更高层任务系统和外部应用，具备明显的平台扩展潜力。",
            "（5）可沉淀性：动作词汇、任务模板、感知服务、接口能力与评测逻辑都可以逐步沉淀为项目资产，支持长期演进。"
        ],
    ),
    (
        "5. OpenArm 真实机器人方向的建设目标",
        [
            "（1）真实机器人接入：OpenArm 方向的首要目标，是让项目具备真实双臂机械臂接入和稳定控制能力，使 capx 不只停留在仿真层面，而能够真正承接现实任务场景。",
            "（2）真实任务闭环：项目并不满足于“机械臂能动起来”，而是希望在真实机器人路径上建立从感知、对齐、接近、接触、抓取到递送和恢复的完整任务闭环。",
            "（3）能力平台化：OpenArm 方向的建设不是为了单次演示，而是为了把真实机器人相关能力纳入 capx 的统一架构中，形成可持续维护、可继续扩展的真实机器人能力平台。",
            "（4）向应用场景过渡：一旦真实机器人链路稳定，后续即可围绕医疗辅助、室内物资递送、人机协同操作等方向逐步扩展场景。"
        ],
    ),
    (
        "6. OpenArm 方向的技术体系设计",
        [
            "（1）执行底座建设：通过双臂执行底座实现机械臂连接、状态读取、动作下发、夹爪控制与到位判断，形成可被系统稳定调用的真实动作能力。",
            "（2）感知底座建设：通过独立感知服务提供目标检测、位置估计、触觉反馈和健康状态检查等功能，为任务执行提供持续的外部反馈信息。",
            "（3）任务层建设：通过任务执行层把动作能力与感知能力组织成闭环流程，使系统能够依据感知结果修正动作，依据触觉反馈决定停止、继续或恢复。",
            "（4）接口层建设：通过网页界面、任务中继和外部接入机制，使 OpenArm 能力不仅能被内部调试使用，也具备对上层应用开放的可能性。",
            "（5）资产层建设：通过姿态、动作模板和组合动作等方式沉淀任务经验，使真实机器人能力从临时脚本逐步转化为长期项目资产。"
        ],
    ),
    (
        "7. 双底座协同机制",
        [
            "（1）执行底座：执行底座负责机械臂真实运动，是实现抓取、递送、放置和复位等行为的基础。该底座强调稳定性、确定性和可控性，是整个系统的物理执行核心。",
            "（2）感知底座：感知底座负责提供目标信息和接触反馈，是实现对齐、接近、避碰、抓稳判断和交互感知的基础。该底座强调实时性、可替换性和结果可解释性。",
            "（3）协同关系：项目并不把感知和控制强行合并为单一模块，而是通过任务执行层将二者有机结合。执行层负责动作，感知层负责反馈，任务层负责决策与调度，从而形成结构清晰的闭环系统。",
            "（4）工程优势：该双底座结构有利于后续分别升级感知和执行能力，也便于在保证核心框架稳定的前提下，逐步引入更复杂的模型、更丰富的传感器与更高级的任务逻辑。"
        ],
    ),
    (
        "8. 动作能力体系建设",
        [
            "（1）稳定姿态建设：项目通过定义一批可复用的稳定姿态，为动作执行提供参考起点、过渡姿态和恢复位置。这有助于提高执行一致性，降低复杂任务中的动作漂移风险。",
            "（2）原子动作建设：项目将双臂动作拆分为一组语义清晰、粒度适中的原子动作，如抬起、下探、展开、内收、夹爪开合等，以便在不同任务中进行复用和纠偏。",
            "（3）组合动作建设：在原子动作基础上，进一步构建多阶段组合动作，用于描述如胸前准备、前伸递送、交接预备、抓取收束等更高层任务段落，提高任务层调用效率。",
            "（4）动作资产沉淀：通过姿态、原子动作和组合动作三层结构，项目逐步把真实机器人经验沉淀为标准化能力资产，为后续的任务泛化与新场景扩展提供支撑。"
        ],
    ),
    (
        "9. 感知能力体系建设",
        [
            "（1）目标识别能力：项目通过视觉感知模块实现目标物识别与位置估计，为抓取、递送和交互任务提供基本的环境理解能力。",
            "（2）空间判断能力：项目进一步利用检测结果支撑对齐、接近和动作修正，使视觉信息不只用于展示，而真正进入任务执行闭环。",
            "（3）触觉反馈能力：项目引入触觉相关结果作为接触和抓取状态判断依据，使系统能够更稳妥地处理下探、接触和抓取收束过程。",
            "（4）服务化能力：感知模块采用相对独立的服务化形式，有利于后续持续升级模型能力、传感器配置和融合逻辑，同时保持上层任务框架的稳定。"
        ],
    ),
    (
        "10. capx 项目的闭环执行思想",
        [
            "（1）视觉参与决策：项目通过检测结果判断目标是否存在、目标大致位于何处，并据此选择后续接近和修正动作。",
            "（2）动作分步执行：系统不倾向于一次性执行过长的不可修正动作，而是通过较小粒度动作推进任务，以便在过程中不断修正状态。",
            "（3）触觉参与收束：在下探和抓取等关键阶段，系统通过触觉反馈判断是否已经接触或是否已形成相对稳定的抓取状态，从而决定是否停止、继续或恢复。",
            "（4）恢复机制参与安全控制：当任务执行失败或状态不符合预期时，系统能够根据既定策略回退到更安全、更易重新组织任务的姿态，保证系统具备可恢复性。"
        ],
    ),
    (
        "11. 双臂能力在项目中的发展价值",
        [
            "（1）单臂能力奠基：在项目早期，单臂能力更适合作为任务闭环验证对象，可优先用于抓取、递送、目标接近和基本交互等功能打样。",
            "（2）双臂能力扩展：在底层双臂能力稳定后，项目可以进一步扩展至双臂协同操作，如双手展开、物体交接、协同支撑和更复杂的空间操作。",
            "（3）平台上限提升：双臂系统的存在意味着 capx 并不是只面向简单抓放，而是具备向更高自由度、更复杂任务流和更真实场景应用扩展的潜力。",
            "（4）系统抽象更完整：双臂能力的引入也会促进姿态体系、动作命名、恢复策略和任务规划层更加规范，从而反过来推动整个项目架构更加成熟。"
        ],
    ),
    (
        "12. 外部接入与系统交互价值",
        [
            "（1）网页交互价值：项目通过网页界面提供状态展示、任务观察和执行反馈能力，使系统不仅能运行，而且能被看见、被理解和被管理。",
            "（2）任务中继价值：通过任务中继机制，系统能够以更标准化的方式接收任务、查询状态、追加输入和停止任务，为更高层业务系统接入预留空间。",
            "（3）外部系统接入价值：该能力使 capx 不再只面向开发人员，而可以逐步面向应用程序、交互前端和场景系统，具备向平台化方向发展的基础条件。",
            "（4）可运维价值：当项目具备健康检查、状态查询、任务管理和外部访问能力后，其工程属性显著增强，更适合真实环境中的长期维护。"
        ],
    ),
    (
        "13. capx 项目的工程化优势",
        [
            "（1）分层清晰：项目在环境、执行、感知、任务与服务等方面具有较清晰的层次结构，有利于多人协作开发与长期维护。",
            "（2）边界明确：不同能力模块之间具有较明确的接口边界，便于独立迭代和替换，降低系统大规模改动时的风险。",
            "（3）便于调试：动作层、感知层和任务层职责分明，使问题定位更直接，也更适合逐段打磨系统性能。",
            "（4）便于扩展：当前项目骨架已经具备承接更多机器人底座、更多感知方式和更多任务模式的潜力，后续能够在不推翻框架的前提下持续扩张能力。"
        ],
    ),
    (
        "14. capx 项目的应用前景",
        [
            "（1）研究应用前景：该项目适合承接机器人智能体、代码生成控制、任务泛化、强化学习后训练等方向的研究与实验。",
            "（2）真实机器人前景：在 OpenArm 等真实机器人方向逐步成熟后，项目可进一步承接递送、抓取、交互式辅助操作等实际任务。",
            "（3）医疗与陪护场景前景：如果结合目标识别、状态感知、人机交互与移动能力，项目未来具备向病房辅助、物资递送、患者交互和护理支持场景扩展的潜力。",
            "（4）平台化前景：随着动作能力、感知能力和接入能力持续积累，capx 有望从研究框架成长为通用机器人任务平台。"
        ],
    ),
    (
        "15. capx 项目的阶段判断",
        [
            "（1）当前阶段：capx 已具备较为清晰的系统骨架，能够支撑仿真任务、模型接入、服务调用以及真实机器人方向的持续建设。",
            "（2）发展特征：项目当前最重要的特点不是功能已经全部完成，而是主线明确、结构稳定、能力边界逐渐清晰，具备继续向深度和广度演进的基础。",
            "（3）阶段价值：对于这类项目而言，能够形成统一框架和稳定主线本身就是重要成果。后续许多具体能力都可以围绕这一主线逐步增强。"
        ],
    ),
    (
        "16. capx 项目的未来建设方向",
        [
            "（1）继续完善真实机器人闭环：进一步提升感知、对齐、抓取、交接和恢复流程的稳定性，形成更成熟的真实机器人任务模板。",
            "（2）继续丰富动作与任务资产：扩充姿态库、原子动作库和组合动作库，使系统具备更强的任务表达与复用能力。",
            "（3）继续增强服务接入能力：完善外部任务接入、状态管理和交互链路，使项目更适合面向上层应用开放。",
            "（4）继续加强评测与训练能力：在项目平台之上承载更多实验对比、智能体策略优化和强化学习迭代工作，提升系统整体能力。",
            "（5）继续向应用场景深化：结合真实机器人和更复杂任务流程，逐步探索在医疗辅助、室内服务和人机协同等方向上的实际应用价值。"
        ],
    ),
    (
        "17. 项目总结",
        [
            "（1）项目总体评价：capx 是一个同时具备研究属性和工程属性的机器人项目，其重点在于构建统一型平台，而非停留于单点功能实现。",
            "（2）OpenArm 方向价值：OpenArm 真实机器人方向使项目进一步具备落地潜力，推动系统从仿真与实验走向真实任务链路建设。",
            "（3）平台发展潜力：随着动作体系、感知体系、任务体系和服务体系不断完善，capx 有望成长为具有长期生命力的机器人任务平台。",
            "（4）综合结论：从项目建设角度看，capx 已经具备较强的发展基础，若继续围绕统一架构、真实闭环和能力沉淀三条主线推进，未来具有较高的研究价值、工程价值与应用价值。"
        ],
    ),
]


def paragraph_xml(text: str, *, style: str | None = None, bold: bool = False, size: int | None = None) -> str:
    ppr = f"<w:pPr><w:pStyle w:val=\"{style}\"/></w:pPr>" if style else ""
    rpr_parts: list[str] = [
        "<w:rPr>",
        "<w:rFonts w:ascii=\"Calibri\" w:hAnsi=\"Calibri\" w:eastAsia=\"等线\" w:cs=\"Calibri\"/>",
    ]
    if bold:
        rpr_parts.append("<w:b/>")
    if size is not None:
        rpr_parts.append(f"<w:sz w:val=\"{size}\"/>")
        rpr_parts.append(f"<w:szCs w:val=\"{size}\"/>")
    rpr_parts.append("</w:rPr>")
    return f"<w:p>{ppr}<w:r>{''.join(rpr_parts)}<w:t xml:space=\"preserve\">{escape(text)}</w:t></w:r></w:p>"


def build_document_xml() -> str:
    body: list[str] = [
        paragraph_xml(TITLE, style="Title", bold=True, size=32),
        paragraph_xml(INTRO, style="BodyText", size=24),
    ]
    for title, paragraphs in SECTIONS:
        body.append(paragraph_xml(title, style="Heading1", bold=True, size=28))
        for paragraph in paragraphs:
            body.append(paragraph_xml(paragraph, style="BodyText", size=24))
    body.append(
        "<w:sectPr>"
        "<w:pgSz w:w=\"11906\" w:h=\"16838\"/>"
        "<w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\" w:header=\"708\" w:footer=\"708\" w:gutter=\"0\"/>"
        "</w:sectPr>"
    )
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document xmlns:wpc=\"http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas\" "
        "xmlns:mc=\"http://schemas.openxmlformats.org/markup-compatibility/2006\" "
        "xmlns:o=\"urn:schemas-microsoft-com:office:office\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" "
        "xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\" "
        "xmlns:v=\"urn:schemas-microsoft-com:vml\" "
        "xmlns:wp14=\"http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing\" "
        "xmlns:wp=\"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing\" "
        "xmlns:w10=\"urn:schemas-microsoft-com:office:word\" "
        "xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" "
        "xmlns:w14=\"http://schemas.microsoft.com/office/word/2010/wordml\" "
        "xmlns:wpg=\"http://schemas.microsoft.com/office/word/2010/wordprocessingGroup\" "
        "xmlns:wpi=\"http://schemas.microsoft.com/office/word/2010/wordprocessingInk\" "
        "xmlns:wne=\"http://schemas.microsoft.com/office/word/2006/wordml\" "
        "xmlns:wps=\"http://schemas.microsoft.com/office/word/2010/wordprocessingShape\" "
        "mc:Ignorable=\"w14 wp14\">"
        f"<w:body>{''.join(body)}</w:body>"
        "</w:document>"
    )


def build_styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault>
      <w:rPr>
        <w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="等线" w:cs="Calibri"/>
        <w:sz w:val="24"/>
        <w:szCs w:val="24"/>
        <w:lang w:val="zh-CN" w:eastAsia="zh-CN" w:bidi="ar-SA"/>
      </w:rPr>
    </w:rPrDefault>
    <w:pPrDefault/>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
    <w:rPr>
      <w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="等线" w:cs="Calibri"/>
      <w:sz w:val="24"/>
      <w:szCs w:val="24"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr>
      <w:jc w:val="center"/>
      <w:spacing w:after="240"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="等线" w:cs="Calibri"/>
      <w:b/>
      <w:sz w:val="32"/>
      <w:szCs w:val="32"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:next w:val="Normal"/>
    <w:qFormat/>
    <w:pPr>
      <w:spacing w:before="240" w:after="120"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="等线" w:cs="Calibri"/>
      <w:b/>
      <w:sz w:val="28"/>
      <w:szCs w:val="28"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="BodyText">
    <w:name w:val="Body Text"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr>
      <w:spacing w:after="120" w:line="360" w:lineRule="auto"/>
      <w:ind w:firstLine="420"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="等线" w:cs="Calibri"/>
      <w:sz w:val="24"/>
      <w:szCs w:val="24"/>
    </w:rPr>
  </w:style>
</w:styles>
"""


def main() -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""
    doc_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""
    core = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>capx项目介绍与技术路线说明</dc:title>
  <dc:creator>OpenAI Codex</dc:creator>
  <cp:lastModifiedBy>OpenAI Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">2026-04-12T00:00:00Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">2026-04-12T00:00:00Z</dcterms:modified>
</cp:coreProperties>
"""
    app = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>OpenAI Codex</Application>
</Properties>
"""

    with ZipFile(OUTPUT_PATH, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("word/document.xml", build_document_xml())
        zf.writestr("word/styles.xml", build_styles_xml())
        zf.writestr("word/_rels/document.xml.rels", doc_rels)
        zf.writestr("docProps/core.xml", core)
        zf.writestr("docProps/app.xml", app)

    print(str(OUTPUT_PATH))


if __name__ == "__main__":
    main()
