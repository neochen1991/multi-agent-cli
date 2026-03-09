import React, { useState } from 'react';
import { Avatar, Button, Empty, Tag, Typography } from 'antd';
import { debateApi } from '@/services/api';

const { Paragraph, Text } = Typography;

type ToolAuditPayload = {
  toolName: string;
  statusLabel?: string;
  requestText?: string;
  responseText?: string;
  auditText?: string;
  focusedText?: string;
};

export type DialogueViewMessage = {
  id: string;
  timeText: string;
  agentName: string;
  side: 'agent' | 'system';
  isMainAgent?: boolean;
  messageKind: 'chat' | 'tool' | 'command' | 'status';
  phase: string;
  eventType: string;
  latencyMs?: number;
  status: 'streaming' | 'done' | 'error';
  summary: string;
  detail: string;
  toolPayload?: ToolAuditPayload;
};

type Props = {
  messages: DialogueViewMessage[];
  streamedMessageText: Record<string, string>;
  expandedDialogueIds: Record<string, boolean>;
  onToggleExpanded: (id: string) => void;
};

const normalizeMarkdownText = (value: string): string =>
  value
    .replace(/\r/g, '')
    .split('\n')
    .map((line) => line.replace(/^\s{0,3}#{1,6}\s+/, '').replace(/^\s*[-*]\s+/, '• '))
    .join('\n');

const buildCompactDetail = (value: string): { text: string; truncated: boolean } => {
  const normalized = normalizeMarkdownText(value || '');
  const lines = normalized.split('\n').map((line) => line.trim());
  if (lines.length === 0) return { text: '', truncated: false };
  const nonEmpty = lines.filter(Boolean);
  const compact = nonEmpty.slice(0, 3).join('\n');
  if (compact.length > 220) {
    return { text: `${compact.slice(0, 220).trim()}...`, truncated: true };
  }
  if (nonEmpty.length > 3) return { text: `${compact}\n...`, truncated: true };
  return { text: compact, truncated: false };
};

const extractOutputRefs = (value: string): string[] => {
  const refs = new Set<string>();
  const text = String(value || '');
  const pattern = /out_[a-f0-9]{8,32}/gi;
  let match = pattern.exec(text);
  while (match) {
    refs.add(String(match[0]));
    match = pattern.exec(text);
  }
  return Array.from(refs);
};

const DialogueStream: React.FC<Props> = ({
  messages,
  streamedMessageText,
  expandedDialogueIds,
  onToggleExpanded,
}) => {
  const kindLabelMap: Record<DialogueViewMessage['messageKind'], string> = {
    chat: '对话',
    tool: '工具调用',
    command: '命令协作',
    status: '状态',
  };
  const [outputRefContent, setOutputRefContent] = useState<Record<string, string>>({});
  const [loadingOutputRef, setLoadingOutputRef] = useState<Record<string, boolean>>({});

  if (messages.length === 0) {
    return <Empty description="暂无匹配的事件明细" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <div className="dialogue-stream discord-thread">
      {messages.map((msg) => {
        const renderedText = streamedMessageText[msg.id] ?? '';
        const fullText = msg.status === 'streaming' ? renderedText : msg.detail;
        const compactView = buildCompactDetail(fullText || msg.detail);
        const compactText = compactView.text;
        const showCursor = msg.status === 'streaming' && renderedText.length < (msg.detail || '').length;
        const isExpanded = Boolean(expandedDialogueIds[msg.id]);
        const canExpand = msg.messageKind === 'tool' ? Boolean((msg.detail || '').trim()) : compactView.truncated;
        const outputRefs = extractOutputRefs(fullText || msg.detail);
        const hasLoadedOutputRef = outputRefs.some((refId) => Boolean(outputRefContent[refId]));
        const kindLabel = kindLabelMap[msg.messageKind] || '消息';
        return (
          <div
            key={msg.id}
            className={`dialogue-row dialogue-row-${msg.messageKind} ${msg.side === 'agent' ? 'dialogue-row-agent' : 'dialogue-row-system'} ${
              msg.isMainAgent ? 'dialogue-row-main-agent' : ''
            }`}
          >
            <Avatar size="small" className={`dialogue-avatar dialogue-avatar-${msg.messageKind}`}>
              {msg.agentName.slice(0, 1).toUpperCase()}
            </Avatar>
            <div className={`dialogue-message dialogue-status-${msg.status}`}>
              <div className="dialogue-meta">
                <Text className="dialogue-username">{msg.agentName}</Text>
                {msg.isMainAgent ? <Tag className="dialogue-main-badge">主Agent</Tag> : null}
                <Text className="dialogue-time">{msg.timeText}</Text>
                <Tag className={`dialogue-kind-tag dialogue-kind-tag-${msg.messageKind}`}>{kindLabel}</Tag>
                {msg.phase && <Tag className="dialogue-tag">{msg.phase}</Tag>}
                <Tag className={`dialogue-tag dialogue-tag-${msg.messageKind}`}>{msg.eventType}</Tag>
                {msg.latencyMs ? <Tag className="dialogue-tag">{`${msg.latencyMs}ms`}</Tag> : null}
              </div>
              <Paragraph className="dialogue-summary">{msg.summary}</Paragraph>
              {msg.messageKind === 'tool' && msg.toolPayload ? (
                <div className="tool-audit-card">
                  <div className="tool-audit-head">
                    <Text className="tool-audit-title">{msg.toolPayload.toolName}</Text>
                    {msg.toolPayload.statusLabel ? <Tag className="tool-audit-status">{msg.toolPayload.statusLabel}</Tag> : null}
                  </div>
                  <div className="tool-audit-grid">
                    <div className="tool-audit-col">
                      <Text className="tool-audit-col-title">请求信息</Text>
                      <pre className="tool-audit-pre">{msg.toolPayload.requestText || '无'}</pre>
                    </div>
                    <div className="tool-audit-col">
                      <Text className="tool-audit-col-title">返回信息</Text>
                      <pre className="tool-audit-pre">{msg.toolPayload.responseText || '无'}</pre>
                    </div>
                  </div>
                  {msg.toolPayload.auditText ? (
                    <div className="tool-audit-foot">
                      <Text className="tool-audit-col-title">调用审计</Text>
                      <pre className="tool-audit-pre">{msg.toolPayload.auditText}</pre>
                    </div>
                  ) : null}
                  {msg.toolPayload.focusedText ? (
                    <div className="tool-audit-foot">
                      <Text className="tool-audit-col-title">分析收获</Text>
                      <pre className="tool-audit-pre">{msg.toolPayload.focusedText}</pre>
                    </div>
                  ) : null}
                </div>
              ) : null}
              {msg.messageKind === 'tool' ? (
                isExpanded ? (
                  <pre className={`dialogue-content dialogue-content-${msg.messageKind}`}>
                    {fullText}
                    {showCursor ? <span className="dialogue-cursor">▋</span> : ''}
                  </pre>
                ) : null
              ) : isExpanded ? (
                <pre className={`dialogue-content dialogue-content-${msg.messageKind}`}>
                  {fullText}
                  {showCursor ? <span className="dialogue-cursor">▋</span> : ''}
                </pre>
              ) : (
                <pre className={`dialogue-content dialogue-content-${msg.messageKind} dialogue-content-compact`}>
                  {compactText || '暂无关键信息'}
                  {showCursor ? <span className="dialogue-cursor">▋</span> : ''}
                </pre>
              )}
              {canExpand && (
                <Button
                  type="link"
                  size="small"
                  className="dialogue-expand-btn"
                  style={{ paddingInline: 0, marginTop: 6 }}
                  onClick={() => onToggleExpanded(msg.id)}
                >
                  {isExpanded ? '收起详情' : msg.messageKind === 'tool' ? '查看原始记录' : '展开详情'}
                </Button>
              )}
              {outputRefs.length > 0 && (
                <div style={{ marginTop: 6 }}>
                  {outputRefs.map((refId) => (
                    <Button
                      key={refId}
                      type="link"
                      size="small"
                      style={{ paddingInline: 0, marginRight: 12 }}
                      loading={Boolean(loadingOutputRef[refId])}
                      onClick={async () => {
                        if (outputRefContent[refId]) {
                          return;
                        }
                        setLoadingOutputRef((prev) => ({ ...prev, [refId]: true }));
                        try {
                          const payload = await debateApi.getOutputRef(refId);
                          if (payload?.found) {
                            setOutputRefContent((prev) => ({ ...prev, [refId]: String(payload.content || '') }));
                          } else {
                            setOutputRefContent((prev) => ({ ...prev, [refId]: '未找到该输出引用内容。' }));
                          }
                        } catch (error: any) {
                          setOutputRefContent((prev) => ({
                            ...prev,
                            [refId]: String(error?.response?.data?.detail || error?.message || '拉取完整输出失败'),
                          }));
                        } finally {
                          setLoadingOutputRef((prev) => ({ ...prev, [refId]: false }));
                        }
                      }}
                    >
                      查看完整输出 {refId}
                    </Button>
                  ))}
                </div>
              )}
              {hasLoadedOutputRef && (
                <div style={{ marginTop: 8 }}>
                  {outputRefs
                    .filter((refId) => Boolean(outputRefContent[refId]))
                    .map((refId) => (
                      <div key={`full_${refId}`} style={{ marginBottom: 8 }}>
                        <Text type="secondary">{`完整输出 ${refId}`}</Text>
                        <pre className="dialogue-content">{outputRefContent[refId]}</pre>
                      </div>
                    ))}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default DialogueStream;
