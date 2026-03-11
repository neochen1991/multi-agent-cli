import React, { useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import { knowledgeApi, type DebateResult, type Report, type KnowledgeEntryType } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Paragraph, Text } = Typography;

type MainConclusion = {
  text: string;
  timeText: string;
  sourceLabel?: string;
} | null;

type SummaryCard = {
  title: string;
  body: string;
};

type ReportSection = {
  title: string;
  body: string;
};

type Props = {
  mainAgentConclusion: MainConclusion;
  debateResult: DebateResult | null;
  sessionStatus: string;
  sessionError: string;
  debateSummaryCards: SummaryCard[];
  reportResult: Report | null;
  reportSections: ReportSection[];
  reportLoading: boolean;
  incidentId: string;
  sessionId: string;
  incidentTitle?: string;
  serviceName?: string;
  debateConfidence?: number;
  sessionQualitySummary?: {
    limitedAnalysis: boolean;
    limitedAgentNames: string[];
    limitedCount: number;
    evidenceGap: boolean;
    riskFactors: string[];
    evidenceCoverage: {
      ok: number;
      degraded: number;
      missing: number;
    };
  };
  onFocusLimitedAnalysis?: () => void;
  onFocusEvidenceGap?: () => void;
  onRegenerateReport: () => Promise<void>;
};

type EvidenceItem = NonNullable<DebateResult['evidence_chain']>[number];

const DebateResultPanel: React.FC<Props> = ({
  mainAgentConclusion,
  debateResult,
  sessionStatus,
  sessionError,
  debateSummaryCards,
  reportResult,
  reportSections,
  reportLoading,
  incidentId,
  sessionId,
  incidentTitle,
  serviceName,
  debateConfidence,
  sessionQualitySummary,
  onFocusLimitedAnalysis,
  onFocusEvidenceGap,
  onRegenerateReport,
}) => {
  const [knowledgeForm] = Form.useForm();
  const [expandedReportSections, setExpandedReportSections] = useState<Record<string, boolean>>({});
  const [expandedSummaryCards, setExpandedSummaryCards] = useState<Record<string, boolean>>({});
  const [expandedTopK, setExpandedTopK] = useState<Record<string, boolean>>({});
  const [expandedEvidence, setExpandedEvidence] = useState<Record<string, boolean>>({});
  const [knowledgeModalOpen, setKnowledgeModalOpen] = useState(false);
  const [savingKnowledge, setSavingKnowledge] = useState(false);
  const confidence = typeof debateConfidence === 'number' ? Number((debateConfidence * 100).toFixed(1)) : null;
  const rootCauseCandidates = Array.isArray(debateResult?.root_cause_candidates) ? debateResult.root_cause_candidates : [];
  const evidenceChain = Array.isArray(debateResult?.evidence_chain) ? debateResult.evidence_chain : [];
  const verificationPlan = Array.isArray(debateResult?.verification_plan) ? debateResult.verification_plan : [];
  const fixRecommendation = debateResult?.fix_recommendation || {};
  const fixSteps = Array.isArray(fixRecommendation.steps) ? fixRecommendation.steps : [];
  const riskLevel = String(debateResult?.risk_assessment?.risk_level || '').toUpperCase();
  const riskFactors = Array.isArray(sessionQualitySummary?.riskFactors) ? sessionQualitySummary?.riskFactors : [];
  const evidenceCoverage = sessionQualitySummary?.evidenceCoverage || { ok: 0, degraded: 0, missing: 0 };
  const coverageTotal = evidenceCoverage.ok + evidenceCoverage.degraded + evidenceCoverage.missing;
  const riskColor =
    riskLevel === 'HIGH' ? 'red' : riskLevel === 'MEDIUM' ? 'orange' : riskLevel === 'LOW' ? 'green' : 'default';
  const strengthColor = (value?: string) => {
    const level = String(value || '').toLowerCase();
    if (level === 'strong') return 'green';
    if (level === 'medium') return 'gold';
    if (level === 'weak') return 'volcano';
    return 'default';
  };
  const reportModuleCards = reportSections.slice(0, 10);
  const topKExists = rootCauseCandidates.length > 0;
  const evidenceExists = evidenceChain.length > 0;
  const hasConclusion = Boolean(mainAgentConclusion?.text?.trim());
  const hasReport = Boolean(reportResult?.content?.trim());
  const sectionThemeColor = (title: string): string => {
    const text = String(title || '').toLowerCase();
    if (text.includes('根因') || text.includes('结论')) return 'blue';
    if (text.includes('证据') || text.includes('链')) return 'cyan';
    if (text.includes('修复') || text.includes('处置')) return 'gold';
    if (text.includes('验证') || text.includes('风险')) return 'purple';
    return 'default';
  };

  const buildSectionPreview = (value: string, maxLines = 6, maxChars = 420): { text: string; truncated: boolean } => {
    const source = String(value || '').trim();
    if (!source) return { text: '', truncated: false };
    const lines = source.split('\n').map((line) => line.trim()).filter(Boolean);
    const joined = lines.join('\n');
    const byLines = lines.slice(0, maxLines).join('\n');
    if (joined.length <= maxChars && lines.length <= maxLines) {
      return { text: joined, truncated: false };
    }
    return {
      text: byLines.slice(0, maxChars).trimEnd() + ' ...',
      truncated: true,
    };
  };

  const buildTextPreview = (value: string, maxLines = 3, maxChars = 220): { text: string; truncated: boolean } => {
    const source = String(value || '').trim();
    if (!source) return { text: '', truncated: false };
    const lines = source.split('\n').map((line) => line.trim()).filter(Boolean);
    const clippedByLines = lines.slice(0, maxLines).join('\n');
    const clipped = clippedByLines.slice(0, maxChars).trimEnd();
    const truncated = lines.length > maxLines || source.length > maxChars;
    return {
      text: truncated ? `${clipped} ...` : clipped,
      truncated,
    };
  };

  const normalizeReportChunk = (value: string): string => {
    let source = String(value || '').trim();
    if (!source) return '';
    if ((source.startsWith('"') && source.endsWith('"')) || (source.startsWith("'") && source.endsWith("'"))) {
      source = source.slice(1, -1);
    }
    source = source
      .replace(/\\n/g, '\n')
      .replace(/\\t/g, '\t')
      .replace(/\\"/g, '"')
      .replace(/^\s*---+\s*$/gm, '---')
      .replace(/\s+---+\s+/g, '\n---\n')
      .replace(/\s+---+\s*$/gm, '\n---')
      .replace(/\s(?=\d+\.\s)/g, '\n')
      .replace(/\s(?=P\d+\.)/g, '\n')
      .replace(/(?:^|\s)•\s+/g, '\n• ')
      .replace(/[ \t]+$/gm, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
    return source;
  };

  const normalizeFreeText = (value: string): string => {
    let source = String(value || '').trim();
    if (!source) return '';
    if ((source.startsWith('"') && source.endsWith('"')) || (source.startsWith("'") && source.endsWith("'"))) {
      source = source.slice(1, -1).trim();
    }
    source = source
      .replace(/\\"/g, '"')
      .replace(/\\n/g, '\n')
      .replace(/\\t/g, '\t')
      .replace(/(?:^|\s)•\s+/g, '\n• ')
      .replace(/[ \t]+$/gm, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
    return source;
  };

  const reportBubbleItems = useMemo(
    () =>
      reportModuleCards.map((section, index) => {
        const normalizedBody = normalizeReportChunk(section.body);
        const id = `${section.title}_${index}`;
        const expanded = Boolean(expandedReportSections[id]);
        const preview = buildSectionPreview(normalizedBody, 6, 420);
        return {
          id,
          expanded,
          section: {
            ...section,
            body: normalizedBody,
          },
          preview,
          align: index % 2 === 0 ? 'left' : 'right',
          color: sectionThemeColor(section.title),
        };
      }),
    [reportModuleCards, expandedReportSections],
  );

  const structuredSummaryItems = useMemo(
    () =>
      debateSummaryCards.map((section, index) => {
        const id = `summary_${section.title}_${index}`;
        const normalizedBody = normalizeReportChunk(section.body);
        const preview = buildSectionPreview(normalizedBody, 6, 480);
        return {
          id,
          index,
          title: section.title,
          body: normalizedBody,
          color: sectionThemeColor(section.title),
          expanded: Boolean(expandedSummaryCards[id]),
          preview,
        };
      }),
    [debateSummaryCards, expandedSummaryCards],
  );

  const toReadableStep = (item: Record<string, unknown>): string => {
    const direct = String(item.summary || item.action || item.step || '').trim();
    if (direct) return direct;
    try {
      return JSON.stringify(item, null, 2);
    } catch {
      return String(item);
    }
  };

  const downloadReport = () => {
    if (!reportResult?.content) return;
    const filename = `incident_report_${reportResult.incident_id}_${reportResult.report_id}.md`;
    const blob = new Blob([reportResult.content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  };

  const splitListText = (value?: string): string[] =>
    String(value || '')
      .split(/[,，;\n；、|]+/)
      .map((item) => item.trim())
      .filter(Boolean);

  const buildKnowledgeSeed = (entryType: KnowledgeEntryType) => {
    const baseTitle = String(incidentTitle || `Incident ${incidentId || sessionId || ''}`).trim();
    const rootCause = String(debateResult?.root_cause || '').trim();
    const summary = rootCause || String(mainAgentConclusion?.text || '').trim();
    const reportBody = String(reportResult?.content || '').trim();
    const reportOutline = reportSections
      .slice(0, 5)
      .map((section) => `## ${section.title}\n${section.body}`)
      .join('\n\n')
      .trim();
    const content = reportBody || reportOutline || summary || '待补充';
    return {
      entry_type: entryType,
      title:
        entryType === 'case'
          ? `${baseTitle} 复盘案例`
          : entryType === 'runbook'
            ? `${baseTitle} 处置 SOP`
            : `${baseTitle} 复盘模板`,
      summary,
      content,
      tags_text: [debateResult?.root_cause_category, serviceName].filter(Boolean).join(', '),
      service_names_text: serviceName || '',
      domain: '',
      aggregate: '',
      author: 'incident-panel',
      case_incident_type: String(debateResult?.root_cause_category || '').trim(),
      case_symptoms_text: baseTitle,
      case_root_cause: rootCause,
      case_solution: String((debateResult?.fix_recommendation as any)?.summary || '').trim(),
      case_fix_steps_text: Array.isArray((debateResult?.fix_recommendation as any)?.testing_requirements)
        ? ((debateResult?.fix_recommendation as any)?.testing_requirements || []).join(', ')
        : '',
      runbook_applicable_text: baseTitle,
      runbook_prechecks_text: Array.isArray(debateResult?.risk_assessment?.risk_factors)
        ? (debateResult?.risk_assessment?.risk_factors || []).join(', ')
        : '',
      runbook_steps_text: Array.isArray((debateResult?.fix_recommendation as any)?.steps)
        ? ((debateResult?.fix_recommendation as any)?.steps || [])
            .map((item: Record<string, unknown>) => String(item.summary || item.step || item.action || '').trim())
            .filter(Boolean)
            .join(', ')
        : '',
      runbook_rollback_text: (debateResult?.fix_recommendation as any)?.rollback_recommended ? '需要准备回滚方案' : '',
      runbook_verification_text: Array.isArray(debateResult?.verification_plan)
        ? (debateResult?.verification_plan || [])
            .map((item: Record<string, unknown>) => String(item.summary || item.check || item.step || '').trim())
            .filter(Boolean)
            .join(', ')
        : '',
      postmortem_impact_text: Array.isArray(debateResult?.impact_analysis?.affected_services)
        ? (debateResult?.impact_analysis?.affected_services || []).join(', ')
        : '',
      postmortem_timeline_text: `发现时间：${mainAgentConclusion?.timeText || '-'}`,
      postmortem_whys_text: rootCause,
      postmortem_actions_text: Array.isArray((debateResult?.risk_assessment as any)?.mitigation_suggestions)
        ? (((debateResult?.risk_assessment as any)?.mitigation_suggestions || []) as string[]).join(', ')
        : '',
    };
  };

  const openKnowledgeModal = (entryType: KnowledgeEntryType) => {
    knowledgeForm.setFieldsValue(buildKnowledgeSeed(entryType));
    setKnowledgeModalOpen(true);
  };

  const handleSaveKnowledge = async () => {
    try {
      await knowledgeForm.validateFields(['entry_type', 'title']);
      const values = knowledgeForm.getFieldsValue(true);
      setSavingKnowledge(true);
      await knowledgeApi.create({
        entry_type: values.entry_type,
        title: String(values.title || '').trim(),
        summary: String(values.summary || '').trim(),
        content: String(values.content || '').trim(),
        tags: splitListText(values.tags_text),
        service_names: splitListText(values.service_names_text),
        domain: String(values.domain || '').trim(),
        aggregate: String(values.aggregate || '').trim(),
        author: String(values.author || '').trim(),
        metadata: {
          source_incident_id: incidentId,
          source_session_id: sessionId,
        },
        case_fields:
          values.entry_type === 'case'
            ? {
                incident_type: String(values.case_incident_type || '').trim(),
                symptoms: splitListText(values.case_symptoms_text),
                root_cause: String(values.case_root_cause || '').trim(),
                solution: String(values.case_solution || '').trim(),
                fix_steps: splitListText(values.case_fix_steps_text),
              }
            : null,
        runbook_fields:
          values.entry_type === 'runbook'
            ? {
                applicable_scenarios: splitListText(values.runbook_applicable_text),
                prechecks: splitListText(values.runbook_prechecks_text),
                steps: splitListText(values.runbook_steps_text),
                rollback_plan: splitListText(values.runbook_rollback_text),
                verification_steps: splitListText(values.runbook_verification_text),
              }
            : null,
        postmortem_fields:
          values.entry_type === 'postmortem_template'
            ? {
                impact_scope_template: splitListText(values.postmortem_impact_text),
                timeline_template: splitListText(values.postmortem_timeline_text),
                five_whys_template: splitListText(values.postmortem_whys_text),
                action_items_template: splitListText(values.postmortem_actions_text),
              }
            : null,
      });
      message.success('已沉淀到知识库');
      setKnowledgeModalOpen(false);
      knowledgeForm.resetFields();
    } catch (error: any) {
      if (error?.errorFields) return;
      message.error(error?.response?.data?.detail || error?.message || '沉淀知识条目失败');
    } finally {
      setSavingKnowledge(false);
    }
  };
  const extractEvidenceTime = (item: EvidenceItem): string => {
    if (!item) return '时间未标注';
    const candidates = [String((item as any).timestamp || ''), String(item.source_ref || ''), String(item.description || '')];
    const patterns = [
      /\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+\-]\d{2}:?\d{2})?/,
      /\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?:\.\d+)?(?:Z|[+\-]\d{2}:?\d{2})?/,
    ];
    for (const text of candidates) {
      if (!text) continue;
      for (const pattern of patterns) {
        const matched = text.match(pattern);
        if (matched?.[0]) {
          return formatBeijingDateTime(matched[0]);
        }
      }
    }
    return '时间未标注';
  };

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card className="module-card" title="诊断总览（OpenDerisk 风格）">
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={15}>
            {hasConclusion ? (
              <div className="rca-summary-card">
                <div className="rca-summary-head">
                  <Space wrap>
                    <Tag color="processing">{mainAgentConclusion?.sourceLabel || '主结论'}</Tag>
                    <Tag color="blue">状态: {sessionStatus || '-'}</Tag>
                    {confidence !== null ? <Tag color="geekblue">置信度: {confidence}%</Tag> : null}
                    {riskLevel ? <Tag color={riskColor}>风险: {riskLevel}</Tag> : null}
                    {sessionQualitySummary?.limitedAnalysis ? (
                      <Tag color="gold" onClick={onFocusLimitedAnalysis} className={onFocusLimitedAnalysis ? 'clickable-tag' : ''}>
                        {`受限分析 ${sessionQualitySummary.limitedCount} 次`}
                      </Tag>
                    ) : null}
                    {sessionQualitySummary?.evidenceGap ? (
                      <Tag color="volcano" onClick={onFocusEvidenceGap} className={onFocusEvidenceGap ? 'clickable-tag' : ''}>
                        关键证据不足
                      </Tag>
                    ) : null}
                  </Space>
                </div>
                <Paragraph className="result-conclusion-paragraph">{mainAgentConclusion?.text || '-'}</Paragraph>
                <Text type="secondary">结论时间：{mainAgentConclusion?.timeText || '-'}</Text>
                {coverageTotal > 0 ? (
                  <div className="rca-coverage-strip">
                    <div className="rca-coverage-head">
                      <span>关键证据覆盖率</span>
                      <Text type="secondary">{`成功 ${evidenceCoverage.ok} / 受限 ${evidenceCoverage.degraded} / 缺失 ${evidenceCoverage.missing}`}</Text>
                    </div>
                    <div className="rca-coverage-bar">
                      <div
                        className="rca-coverage-segment ok"
                        style={{ width: `${(evidenceCoverage.ok / coverageTotal) * 100}%` }}
                      />
                      <div
                        className="rca-coverage-segment degraded"
                        style={{ width: `${(evidenceCoverage.degraded / coverageTotal) * 100}%` }}
                      />
                      <div
                        className="rca-coverage-segment missing"
                        style={{ width: `${(evidenceCoverage.missing / coverageTotal) * 100}%` }}
                      />
                    </div>
                  </div>
                ) : null}
                {(sessionQualitySummary?.limitedAnalysis || sessionQualitySummary?.evidenceGap) ? (
                  <div className="rca-quality-callout">
                    <Space wrap size={[6, 6]}>
                      {sessionQualitySummary?.limitedAnalysis ? (
                        <Tag color="gold" onClick={onFocusLimitedAnalysis} className={onFocusLimitedAnalysis ? 'clickable-tag' : ''}>
                          {`受限分析 ${sessionQualitySummary.limitedCount} 次`}
                        </Tag>
                      ) : null}
                      {sessionQualitySummary?.limitedAgentNames?.map((agent) => (
                        <Tag key={agent}>{agent}</Tag>
                      ))}
                      {sessionQualitySummary?.evidenceGap ? (
                        <Tag color="volcano" onClick={onFocusEvidenceGap} className={onFocusEvidenceGap ? 'clickable-tag' : ''}>
                          关键证据不足
                        </Tag>
                      ) : null}
                    </Space>
                    <Paragraph className="rca-quality-callout-text">
                      {sessionQualitySummary?.limitedAnalysis
                        ? '部分专家 Agent 未完成真实工具取证，当前结论包含基于已有证据的受限分析。'
                        : '当前结论不包含受限分析。'}
                      {sessionQualitySummary?.evidenceGap
                        ? ' Judge 已将本次会话标记为关键证据不足，当前结论应按低置信度处理。'
                        : ''}
                    </Paragraph>
                    {riskFactors.length > 0 ? (
                      <div className="rca-quality-risk-list">
                        {riskFactors.slice(0, 4).map((item) => (
                          <div key={item} className="rca-quality-risk-item">
                            {item}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : sessionStatus === 'failed' ? (
              <Alert type="error" showIcon message={`辩论失败：${sessionError || '请查看辩论过程中的错误详情'}`} />
            ) : sessionStatus === 'completed' ? (
              <Alert
                type="warning"
                showIcon
                message="当前会话未生成有效主结论，请补充日志细节后重新发起分析。"
              />
            ) : (
              <Alert type="info" showIcon message="主 Agent 结论尚未生成，请先完成辩论过程。" />
            )}
          </Col>
          <Col xs={24} lg={9}>
            <div className="rca-overview-kpis">
              <div className="rca-overview-kpi">
                <span>Top-K 候选</span>
                <strong>{rootCauseCandidates.length}</strong>
              </div>
              <div className="rca-overview-kpi">
                <span>证据链条数</span>
                <strong>{evidenceChain.length}</strong>
              </div>
              <div className="rca-overview-kpi">
                <span>验证项</span>
                <strong>{verificationPlan.length}</strong>
              </div>
              <div className="rca-overview-kpi">
                <span>报告模块</span>
                <strong>{reportSections.length}</strong>
              </div>
            </div>
            <Descriptions size="small" column={1} styles={{ label: { width: 90 } }} style={{ marginTop: 10 }}>
              <Descriptions.Item label="会话 ID">{sessionId || '-'}</Descriptions.Item>
              <Descriptions.Item label="Incident">{incidentId || '-'}</Descriptions.Item>
              <Descriptions.Item label="根因分类">{debateResult?.root_cause_category || '-'}</Descriptions.Item>
            </Descriptions>
          </Col>
        </Row>
      </Card>

      <Card className="module-card" title="结构化辩论结果">
        {debateSummaryCards.length === 0 ? (
          <Empty description="结构化结果暂不可用，请先完成辩论流程" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div>
            <Space size={8} style={{ marginBottom: 8 }}>
              <Button
                size="small"
                onClick={() =>
                  setExpandedSummaryCards((prev) => {
                    const next = { ...prev };
                    structuredSummaryItems.forEach((item) => {
                      if (item.preview.truncated) next[item.id] = true;
                    });
                    return next;
                  })
                }
              >
                全部展开
              </Button>
              <Button
                size="small"
                onClick={() =>
                  setExpandedSummaryCards((prev) => {
                    const next = { ...prev };
                    structuredSummaryItems.forEach((item) => {
                      next[item.id] = false;
                    });
                    return next;
                  })
                }
              >
                全部收起
              </Button>
            </Space>
            <div className="summary-card-list">
              {structuredSummaryItems.map((item) => (
                <div className="summary-card-row" key={item.id}>
                  <div className="summary-card-avatar">{item.index + 1}</div>
                  <div className="summary-card-body">
                    <div className="summary-card-head">
                      <Tag color={item.color}>{item.title}</Tag>
                    </div>
                    <pre className="summary-card-content">
                      {item.expanded ? item.body : item.preview.text || '暂无内容'}
                    </pre>
                    {item.preview.truncated ? (
                      <Button
                        type="link"
                        size="small"
                        style={{ paddingInline: 0 }}
                        onClick={() =>
                          setExpandedSummaryCards((prev) => ({
                            ...prev,
                            [item.id]: !prev[item.id],
                          }))
                        }
                      >
                        {item.expanded ? '收起' : '展开详情'}
                      </Button>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      <Card
        className="module-card"
        title="报告与可视化结果"
        extra={
          <Space>
            <Button onClick={downloadReport} disabled={!hasReport}>
              下载报告
            </Button>
            <Select
              size="small"
              defaultValue="case"
              style={{ width: 142 }}
              onSelect={(value) => openKnowledgeModal(value as KnowledgeEntryType)}
              options={[
                { label: '沉淀为运维案例', value: 'case' },
                { label: '沉淀为 SOP', value: 'runbook' },
                { label: '沉淀为复盘模板', value: 'postmortem_template' },
              ]}
            />
            <Button loading={reportLoading} onClick={() => void onRegenerateReport()} disabled={!incidentId}>
              重新生成报告
            </Button>
          </Space>
        }
      >
        {reportResult ? (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Space size="large" wrap>
              <Statistic title="报告分段" value={reportSections.length} />
              <Statistic title="生成状态" value={reportSections.length > 0 ? '完成' : '空报告'} />
              <Statistic title="证据条数" value={evidenceChain.length} />
              <Statistic title="Top-K 候选" value={rootCauseCandidates.length} />
            </Space>
            <Descriptions size="small" column={2} styles={{ label: { width: 90 } }}>
              <Descriptions.Item label="报告 ID">{reportResult.report_id}</Descriptions.Item>
              <Descriptions.Item label="生成时间">{formatBeijingDateTime(reportResult.generated_at)}</Descriptions.Item>
              <Descriptions.Item label="输出格式">{reportResult.format}</Descriptions.Item>
              <Descriptions.Item label="会话 ID">{reportResult.debate_session_id || sessionId || '-'}</Descriptions.Item>
            </Descriptions>
            <Tabs
              items={[
                {
                  key: 'visual',
                  label: '证据与候选',
                  children: (
                    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                      <Card size="small" title="根因总览">
                        <Row gutter={[16, 16]} align="middle">
                          <Col xs={24} md={8}>
                            <Space direction="vertical" size={8} style={{ width: '100%', alignItems: 'center' }}>
                              <Progress type="circle" percent={confidence || 0} size={88} />
                              <Text type="secondary">整体置信度</Text>
                            </Space>
                          </Col>
                          <Col xs={24} md={16}>
                            <Space direction="vertical" size={8} style={{ width: '100%' }}>
                              <Text strong>{String(debateResult?.root_cause || '暂无根因')}</Text>
                              <Space wrap>
                                {riskLevel ? <Tag color={riskColor}>风险等级: {riskLevel}</Tag> : null}
                                <Tag color="blue">证据链: {evidenceChain.length}</Tag>
                                <Tag color="geekblue">Top-K: {rootCauseCandidates.length}</Tag>
                                <Tag color="purple">验证项: {verificationPlan.length}</Tag>
                                <Tag color={debateResult?.cross_source_passed ? 'green' : 'orange'}>
                                  跨源证据门禁: {debateResult?.cross_source_passed ? '通过' : '未通过'}
                                </Tag>
                              </Space>
                            </Space>
                          </Col>
                        </Row>
                      </Card>
                      <Row gutter={[16, 16]}>
                        <Col xs={24} lg={12}>
                          <Card size="small" title="Top-K 根因候选（排序+区间）">
                            {!topKExists ? (
                              <Alert type="info" showIcon message="暂无 Top-K 根因候选" />
                            ) : (
                              <div className="rca-topk-list">
                                {rootCauseCandidates.slice(0, 5).map((item, index) => {
                                  const percent = Math.max(0, Math.min(100, Number((item.confidence || 0) * 100)));
                                  const ci = Array.isArray(item.confidence_interval) ? item.confidence_interval : [];
                                  const low = Math.max(0, Math.min(100, Number(ci[0] || 0) * 100));
                                  const high = Math.max(0, Math.min(100, Number(ci[1] || 0) * 100));
                                  const intervalLeft = Math.min(low, high);
                                  const intervalWidth = Math.max(2, Math.abs(high - low));
                                  const refs = Array.isArray(item.evidence_refs) ? item.evidence_refs : [];
                                  const key = `topk_${item.rank || index}`;
                                  const expanded = Boolean(expandedTopK[key]);
                                  const normalizedSummary = normalizeFreeText(String(item.summary || '-'));
                                  const summaryPreview = buildTextPreview(normalizedSummary, 3, 260);
                                  const coverage = Number((item as any).evidence_coverage_count || 0);
                                  const conflicts = Array.isArray((item as any).conflict_points)
                                    ? ((item as any).conflict_points as string[])
                                    : [];
                                  const uncertainties = Array.isArray((item as any).uncertainty_sources)
                                    ? ((item as any).uncertainty_sources as string[])
                                    : [];
                                  return (
                                    <div className={`rca-topk-item ${index === 0 ? 'is-top' : ''}`} key={`${item.rank || index}_${item.summary}`}>
                                      <div className="rca-topk-rank">#{item.rank || index + 1}</div>
                                      <div className="rca-topk-main">
                                        <Space className="rca-topk-head" align="start">
                                          <pre className="rca-topk-summary-block">
                                            {expanded ? normalizedSummary : summaryPreview.text}
                                          </pre>
                                          <Space size={6} wrap>
                                            <Tag>{String(item.source_agent || 'unknown')}</Tag>
                                            <Tag color={index === 0 ? 'gold' : 'blue'}>{percent.toFixed(1)}%</Tag>
                                          </Space>
                                        </Space>
                                        {summaryPreview.truncated ? (
                                          <Button
                                            type="link"
                                            size="small"
                                            style={{ paddingInline: 0, marginTop: -2 }}
                                            onClick={() =>
                                              setExpandedTopK((prev) => ({
                                                ...prev,
                                                [key]: !prev[key],
                                              }))
                                            }
                                          >
                                            {expanded ? '收起候选详情' : '展开候选详情'}
                                          </Button>
                                        ) : null}
                                        <div className="rca-topk-bar">
                                          <div className="rca-topk-bar-fill" style={{ width: `${percent}%` }} />
                                          <div
                                            className="rca-topk-bar-interval"
                                            style={{ left: `${intervalLeft}%`, width: `${intervalWidth}%` }}
                                          />
                                        </div>
                                        <Text type="secondary" className="rca-topk-interval">
                                          置信区间 [{low.toFixed(1)}%, {high.toFixed(1)}%]
                                        </Text>
                                        <Space wrap size={[6, 6]}>
                                          <Tag color="blue">覆盖证据: {coverage}</Tag>
                                          {conflicts.length > 0 ? <Tag color="volcano">冲突点: {conflicts.length}</Tag> : null}
                                          {uncertainties.length > 0 ? <Tag color="gold">不确定性: {uncertainties.length}</Tag> : null}
                                        </Space>
                                        {conflicts.length > 0 ? (
                                          <div className="rca-topk-refs">
                                            {conflicts.slice(0, 3).map((text, idx2) => (
                                              <Tag key={`conflict_${idx2}_${text}`} color="volcano">
                                                冲突: {text}
                                              </Tag>
                                            ))}
                                          </div>
                                        ) : null}
                                        {uncertainties.length > 0 ? (
                                          <div className="rca-topk-refs">
                                            {uncertainties.slice(0, 3).map((text, idx2) => (
                                              <Tag key={`uncertainty_${idx2}_${text}`} color="gold">
                                                不确定性: {text}
                                              </Tag>
                                            ))}
                                          </div>
                                        ) : null}
                                        {refs.length > 0 ? (
                                          <div className="rca-topk-refs">
                                            {refs.slice(0, 8).map((ref) => (
                                              <Tag key={ref} color="cyan">
                                                {ref}
                                              </Tag>
                                            ))}
                                          </div>
                                        ) : null}
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </Card>
                        </Col>
                        <Col xs={24} lg={12}>
                          <Card size="small" title="证据链（时间线）">
                            {!evidenceExists ? (
                              <Alert type="info" showIcon message="暂无证据链" />
                            ) : (
                              <div className="rca-evidence-chain">
                                {evidenceChain.slice(0, 12).map((item, idx, arr) => (
                                  <div className="rca-evidence-item" key={`${item.evidence_id || idx}_${item.source || ''}`}>
                                    <div className="rca-evidence-axis">
                                      <span className={`rca-evidence-dot strength-${String(item.strength || 'unknown').toLowerCase()}`} />
                                      {idx < arr.length - 1 ? <span className="rca-evidence-line" /> : null}
                                    </div>
                                    <div className="rca-evidence-card">
                                      <Space wrap size={[6, 6]}>
                                        <Tag color="blue">{item.type || 'evidence'}</Tag>
                                        <Tag>{item.source || '-'}</Tag>
                                        {item.evidence_id ? <Tag>#{item.evidence_id}</Tag> : null}
                                        {item.strength ? <Tag color={strengthColor(item.strength)}>{item.strength}</Tag> : null}
                                        <Tag color="cyan">{extractEvidenceTime(item)}</Tag>
                                      </Space>
                                      {(() => {
                                        const key = `evidence_${item.evidence_id || idx}`;
                                        const expanded = Boolean(expandedEvidence[key]);
                                        const normalizedDescription = normalizeFreeText(String(item.description || '-'));
                                        const preview = buildTextPreview(normalizedDescription, 3, 280);
                                        return (
                                          <>
                                            <pre className="rca-evidence-desc-pre">
                                              {expanded ? normalizedDescription : preview.text}
                                            </pre>
                                            {preview.truncated ? (
                                              <Button
                                                size="small"
                                                type="link"
                                                style={{ paddingInline: 0, marginTop: -4 }}
                                                onClick={() =>
                                                  setExpandedEvidence((prev) => ({
                                                    ...prev,
                                                    [key]: !prev[key],
                                                  }))
                                                }
                                              >
                                                {expanded ? '收起证据详情' : '展开证据详情'}
                                              </Button>
                                            ) : null}
                                          </>
                                        );
                                      })()}
                                      {item.source_ref || item.location ? (
                                        <Text type="secondary" className="rca-evidence-ref">
                                          引用：{item.source_ref || '-'} {item.location ? `@ ${item.location}` : ''}
                                        </Text>
                                      ) : null}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </Card>
                        </Col>
                      </Row>
                    </Space>
                  ),
                },
                {
                  key: 'action_plan',
                  label: '处置与验证',
                  children: (
                    <Row gutter={[16, 16]}>
                      <Col xs={24} lg={12}>
                        <Card size="small" title="修复步骤（Step Card）">
                          {fixSteps.length === 0 ? (
                            <Alert type="info" showIcon message="暂无修复步骤建议" />
                          ) : (
                            <div className="rca-action-list">
                              {fixSteps.slice(0, 8).map((item, index) => (
                                <div className="rca-action-step" key={`fix_${index}`}>
                                  <div className="rca-action-index">{index + 1}</div>
                                  <div className="rca-action-body">{toReadableStep(item as Record<string, unknown>)}</div>
                                </div>
                              ))}
                            </div>
                          )}
                          {fixRecommendation.summary ? (
                            <Alert
                              type="success"
                              showIcon
                              style={{ marginTop: 10 }}
                              message={String(fixRecommendation.summary)}
                            />
                          ) : null}
                        </Card>
                      </Col>
                      <Col xs={24} lg={12}>
                        <Card size="small" title="验证计划">
                          {verificationPlan.length === 0 ? (
                            <Alert type="info" showIcon message="暂无验证计划" />
                          ) : (
                            <List
                              size="small"
                              dataSource={verificationPlan.slice(0, 10)}
                              renderItem={(item, index) => {
                                const row = item as Record<string, unknown>;
                                const objective = String(row.objective || '-');
                                const dimension = String(row.dimension || '-');
                                const criteria = String(row.pass_criteria || '-');
                                return (
                                  <List.Item>
                                    <div className="rca-verify-item">
                                      <div className="rca-verify-title">{index + 1}. [{dimension}] {objective}</div>
                                      <div className="rca-verify-criteria">通过标准：{criteria}</div>
                                    </div>
                                  </List.Item>
                                );
                              }}
                            />
                          )}
                        </Card>
                      </Col>
                    </Row>
                  ),
                },
                {
                  key: 'modules',
                  label: '报告模块',
                  children:
                    reportModuleCards.length === 0 ? (
                      <Alert type="info" showIcon message="报告模块为空，请重新生成报告。" />
                    ) : (
                      <div>
                        <Space size={8} style={{ marginBottom: 8 }}>
                          <Button
                            size="small"
                            onClick={() =>
                              setExpandedReportSections((prev) => {
                                const next = { ...prev };
                                reportBubbleItems.forEach((item) => {
                                  if (item.preview.truncated) next[item.id] = true;
                                });
                                return next;
                              })
                            }
                          >
                            全部展开
                          </Button>
                          <Button
                            size="small"
                            onClick={() =>
                              setExpandedReportSections((prev) => {
                                const next = { ...prev };
                                reportBubbleItems.forEach((item) => {
                                  next[item.id] = false;
                                });
                                return next;
                              })
                            }
                          >
                            全部收起
                          </Button>
                        </Space>
                        <div className="report-bubble-list">
                          {reportBubbleItems.map((item, index) => (
                            <div key={item.id} className={`report-bubble-row align-${item.align}`}>
                              <div className="report-bubble-avatar">{index + 1}</div>
                              <div className="report-bubble-card">
                                <div className="report-bubble-head">
                                  <Tag color={item.color}>{item.section.title}</Tag>
                                  <Text type="secondary">模块 {index + 1}</Text>
                                </div>
                                <pre className="report-bubble-body">
                                  {item.expanded ? item.section.body : item.preview.text || '暂无内容'}
                                </pre>
                                {item.preview.truncated ? (
                                  <Button
                                    size="small"
                                    type="link"
                                    style={{ paddingInline: 0 }}
                                    onClick={() =>
                                      setExpandedReportSections((prev) => ({
                                        ...prev,
                                        [item.id]: !prev[item.id],
                                      }))
                                    }
                                  >
                                    {item.expanded ? '收起' : '展开完整模块'}
                                  </Button>
                                ) : null}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ),
                },
                {
                  key: 'raw',
                  label: '原始分段',
                  children:
                    reportSections.length === 0 ? (
                      <Alert type="info" showIcon message="报告内容为空，请点击“重新生成报告”后重试。" />
                    ) : (
                      <div className="report-raw-timeline">
                        {reportSections.map((section, index) => {
                          const normalizedBody = normalizeReportChunk(section.body);
                          const id = `raw_${section.title}_${index}`;
                          const expanded = Boolean(expandedReportSections[id]);
                          const preview = buildSectionPreview(normalizedBody, 8, 680);
                          return (
                            <div className="report-raw-item" key={id}>
                              <div className="report-raw-axis">
                                <span className="report-raw-dot" />
                                {index < reportSections.length - 1 ? <span className="report-raw-line" /> : null}
                              </div>
                              <div className="report-raw-card">
                                <div className="report-raw-head">
                                  <Tag color={sectionThemeColor(section.title)}>{section.title}</Tag>
                                  <Text type="secondary">段落 {index + 1}</Text>
                                </div>
                                <pre className="report-raw-body">
                                  {expanded ? normalizedBody : preview.text || '暂无内容'}
                                </pre>
                                {preview.truncated ? (
                                  <Button
                                    size="small"
                                    type="link"
                                    style={{ paddingInline: 0 }}
                                    onClick={() =>
                                      setExpandedReportSections((prev) => ({
                                        ...prev,
                                        [id]: !prev[id],
                                      }))
                                    }
                                  >
                                    {expanded ? '收起' : '展开完整段落'}
                                  </Button>
                                ) : null}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ),
                },
              ]}
            />
          </Space>
        ) : (
          <Empty description="暂未生成报告，请先完成辩论或点击“重新生成报告”" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>
      <Modal
        title="沉淀到知识库"
        open={knowledgeModalOpen}
        onCancel={() => setKnowledgeModalOpen(false)}
        onOk={() => void handleSaveKnowledge()}
        confirmLoading={savingKnowledge}
        width={760}
        destroyOnHidden
      >
        <Form form={knowledgeForm} layout="vertical">
          <Form.Item name="entry_type" label="类型" rules={[{ required: true, message: '请选择类型' }]}>
            <Select
              options={[
                { label: '运维案例', value: 'case' },
                { label: 'Runbook / SOP', value: 'runbook' },
                { label: '复盘模板', value: 'postmortem_template' },
              ]}
            />
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="summary" label="摘要">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="content" label="正文">
            <Input.TextArea rows={8} />
          </Form.Item>
          <Form.Item name="tags_text" label="标签（逗号分隔）">
            <Input />
          </Form.Item>
          <Form.Item name="service_names_text" label="关联服务（逗号分隔）">
            <Input />
          </Form.Item>
          <Form.Item name="author" label="作者">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
};

export default DebateResultPanel;
