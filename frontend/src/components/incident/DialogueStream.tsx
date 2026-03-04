import React, { useState } from 'react';
import { Avatar, Button, Empty, Tag, Typography } from 'antd';
import { debateApi } from '@/services/api';

const { Paragraph, Text } = Typography;

export type DialogueViewMessage = {
  id: string;
  timeText: string;
  agentName: string;
  side: 'agent' | 'system';
  phase: string;
  eventType: string;
  latencyMs?: number;
  status: 'streaming' | 'done' | 'error';
  summary: string;
  detail: string;
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
        const canExpand = compactView.truncated;
        const outputRefs = extractOutputRefs(fullText || msg.detail);
        const hasLoadedOutputRef = outputRefs.some((refId) => Boolean(outputRefContent[refId]));
        return (
          <div
            key={msg.id}
            className={`dialogue-row ${msg.side === 'agent' ? 'dialogue-row-agent' : 'dialogue-row-system'}`}
          >
            <Avatar size="small" className="dialogue-avatar">
              {msg.agentName.slice(0, 1).toUpperCase()}
            </Avatar>
            <div className={`dialogue-message dialogue-status-${msg.status}`}>
              <div className="dialogue-meta">
                <Text className="dialogue-username">{msg.agentName}</Text>
                <Text className="dialogue-time">{msg.timeText}</Text>
                {msg.phase && <Tag className="dialogue-tag">{msg.phase}</Tag>}
                <Tag className="dialogue-tag">{msg.eventType}</Tag>
                {msg.latencyMs ? <Tag className="dialogue-tag">{`${msg.latencyMs}ms`}</Tag> : null}
              </div>
              <Paragraph className="dialogue-summary">{msg.summary}</Paragraph>
              {isExpanded ? (
                <pre className="dialogue-content">
                  {fullText}
                  {showCursor ? <span className="dialogue-cursor">▋</span> : ''}
                </pre>
              ) : (
                <pre className="dialogue-content dialogue-content-compact">
                  {compactText || '暂无关键信息'}
                  {showCursor ? <span className="dialogue-cursor">▋</span> : ''}
                </pre>
              )}
              {canExpand && (
                <Button type="link" size="small" style={{ paddingInline: 0, marginTop: 6 }} onClick={() => onToggleExpanded(msg.id)}>
                  {isExpanded ? '收起详情' : '展开详情'}
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
