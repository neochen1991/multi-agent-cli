import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  knowledgeApi,
  type KnowledgeEntry,
  type KnowledgeEntryType,
} from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

type EntryFormValues = {
  entry_type: KnowledgeEntryType;
  title: string;
  summary: string;
  content: string;
  tags_text: string;
  service_names_text: string;
  domain: string;
  aggregate: string;
  author: string;
  case_incident_type: string;
  case_symptoms_text: string;
  case_root_cause: string;
  case_solution: string;
  case_fix_steps_text: string;
  runbook_applicable_text: string;
  runbook_prechecks_text: string;
  runbook_steps_text: string;
  runbook_rollback_text: string;
  runbook_verification_text: string;
  postmortem_impact_text: string;
  postmortem_timeline_text: string;
  postmortem_whys_text: string;
  postmortem_actions_text: string;
};

const splitTextList = (value?: string): string[] =>
  String(value || '')
    .split(/[,，;\n；、|]+/)
    .map((item) => item.trim())
    .filter(Boolean);

const joinTextList = (items?: string[]): string => (items || []).join('、');

const emptyFormValues: EntryFormValues = {
  entry_type: 'case',
  title: '',
  summary: '',
  content: '',
  tags_text: '',
  service_names_text: '',
  domain: '',
  aggregate: '',
  author: '',
  case_incident_type: '',
  case_symptoms_text: '',
  case_root_cause: '',
  case_solution: '',
  case_fix_steps_text: '',
  runbook_applicable_text: '',
  runbook_prechecks_text: '',
  runbook_steps_text: '',
  runbook_rollback_text: '',
  runbook_verification_text: '',
  postmortem_impact_text: '',
  postmortem_timeline_text: '',
  postmortem_whys_text: '',
  postmortem_actions_text: '',
};

const typeLabel: Record<KnowledgeEntryType, string> = {
  case: '运维案例',
  runbook: 'Runbook / SOP',
  postmortem_template: '复盘模板',
};

const buildPayload = (values: EntryFormValues) => ({
  entry_type: values.entry_type,
  title: values.title.trim(),
  summary: values.summary.trim(),
  content: values.content.trim(),
  tags: splitTextList(values.tags_text),
  service_names: splitTextList(values.service_names_text),
  domain: values.domain.trim(),
  aggregate: values.aggregate.trim(),
  author: values.author.trim(),
  metadata: {},
  case_fields:
    values.entry_type === 'case'
      ? {
          incident_type: values.case_incident_type.trim(),
          symptoms: splitTextList(values.case_symptoms_text),
          root_cause: values.case_root_cause.trim(),
          solution: values.case_solution.trim(),
          fix_steps: splitTextList(values.case_fix_steps_text),
        }
      : null,
  runbook_fields:
    values.entry_type === 'runbook'
      ? {
          applicable_scenarios: splitTextList(values.runbook_applicable_text),
          prechecks: splitTextList(values.runbook_prechecks_text),
          steps: splitTextList(values.runbook_steps_text),
          rollback_plan: splitTextList(values.runbook_rollback_text),
          verification_steps: splitTextList(values.runbook_verification_text),
        }
      : null,
  postmortem_fields:
    values.entry_type === 'postmortem_template'
      ? {
          impact_scope_template: splitTextList(values.postmortem_impact_text),
          timeline_template: splitTextList(values.postmortem_timeline_text),
          five_whys_template: splitTextList(values.postmortem_whys_text),
          action_items_template: splitTextList(values.postmortem_actions_text),
        }
      : null,
});

const toFormValues = (entry?: KnowledgeEntry | null): EntryFormValues => {
  if (!entry) return { ...emptyFormValues };
  return {
    entry_type: entry.entry_type,
    title: entry.title || '',
    summary: entry.summary || '',
    content: entry.content || '',
    tags_text: (entry.tags || []).join(', '),
    service_names_text: (entry.service_names || []).join(', '),
    domain: entry.domain || '',
    aggregate: entry.aggregate || '',
    author: entry.author || '',
    case_incident_type: entry.case_fields?.incident_type || '',
    case_symptoms_text: (entry.case_fields?.symptoms || []).join(', '),
    case_root_cause: entry.case_fields?.root_cause || '',
    case_solution: entry.case_fields?.solution || '',
    case_fix_steps_text: (entry.case_fields?.fix_steps || []).join(', '),
    runbook_applicable_text: (entry.runbook_fields?.applicable_scenarios || []).join(', '),
    runbook_prechecks_text: (entry.runbook_fields?.prechecks || []).join(', '),
    runbook_steps_text: (entry.runbook_fields?.steps || []).join(', '),
    runbook_rollback_text: (entry.runbook_fields?.rollback_plan || []).join(', '),
    runbook_verification_text: (entry.runbook_fields?.verification_steps || []).join(', '),
    postmortem_impact_text: (entry.postmortem_fields?.impact_scope_template || []).join(', '),
    postmortem_timeline_text: (entry.postmortem_fields?.timeline_template || []).join(', '),
    postmortem_whys_text: (entry.postmortem_fields?.five_whys_template || []).join(', '),
    postmortem_actions_text: (entry.postmortem_fields?.action_items_template || []).join(', '),
  };
};

const KnowledgePage: React.FC = () => {
  const [form] = Form.useForm<EntryFormValues>();
  const [items, setItems] = useState<KnowledgeEntry[]>([]);
  const [stats, setStats] = useState({ total: 0, case: 0, runbook: 0, postmortem_template: 0 });
  const [loading, setLoading] = useState(false);
  const [filterType, setFilterType] = useState<KnowledgeEntryType>('case');
  const [filterQ, setFilterQ] = useState('');
  const [filterTag, setFilterTag] = useState('');
  const [drawerEntry, setDrawerEntry] = useState<KnowledgeEntry | null>(null);
  const [editingEntry, setEditingEntry] = useState<KnowledgeEntry | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [listRes, statsRes] = await Promise.all([
        knowledgeApi.list({
          entry_type: filterType,
          q: filterQ.trim() || undefined,
          tag: filterTag.trim() || undefined,
        }),
        knowledgeApi.stats(),
      ]);
      setItems(listRes.items || []);
      setStats(statsRes);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '加载知识库失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterType]);

  const tagOptions = useMemo(() => {
    const set = new Set<string>();
    items.forEach((item) => (item.tags || []).forEach((tag) => set.add(tag)));
    return Array.from(set).sort().map((tag) => ({ label: tag, value: tag }));
  }, [items]);

  const columns: ColumnsType<KnowledgeEntry> = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (value: string, row) => (
        <Space direction="vertical" size={2}>
          <Text strong>{value || '-'}</Text>
          <Text type="secondary">{row.summary || '-'}</Text>
        </Space>
      ),
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      width: 240,
      render: (tags: string[]) =>
        tags?.length ? (
          <Space wrap size={[4, 4]}>
            {tags.map((tag) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
          </Space>
        ) : (
          '-'
        ),
    },
    {
      title: '关联域',
      key: 'scope',
      width: 220,
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Text>{row.domain || '-'}</Text>
          <Text type="secondary">{row.aggregate || '-'}</Text>
        </Space>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (value: string) => formatBeijingDateTime(value, '-').replace(' (北京时间)', ''),
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_, row) => (
        <Space size={0}>
          <Button type="link" size="small" onClick={() => setDrawerEntry(row)}>
            查看
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setEditingEntry(row);
              form.setFieldsValue(toFormValues(row));
              setModalOpen(true);
            }}
          >
            编辑
          </Button>
          <Popconfirm title="确认删除这条知识条目？" onConfirm={() => void handleDelete(row.id)}>
            <Button type="link" size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const handleDelete = async (entryId: string) => {
    try {
      await knowledgeApi.delete(entryId);
      message.success('已删除知识条目');
      if (drawerEntry?.id === entryId) setDrawerEntry(null);
      await loadAll();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '删除失败');
    }
  };

  const openCreate = (entryType?: KnowledgeEntryType) => {
    setEditingEntry(null);
    form.setFieldsValue({ ...emptyFormValues, entry_type: entryType || filterType });
    setModalOpen(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const payload = buildPayload(values);
      if (editingEntry) {
        await knowledgeApi.update(editingEntry.id, payload);
        message.success('知识条目已更新');
      } else {
        await knowledgeApi.create(payload);
        message.success('知识条目已创建');
      }
      setModalOpen(false);
      setEditingEntry(null);
      form.resetFields();
      await loadAll();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.response?.data?.detail || e?.message || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const entryType = Form.useWatch('entry_type', form) || 'case';

  return (
    <div className="knowledge-page">
      <Card className="module-card" style={{ marginBottom: 16 }}>
        <Title level={4} style={{ marginTop: 0, marginBottom: 8 }}>
          知识库中心
        </Title>
        <Paragraph style={{ marginBottom: 8 }}>
          统一管理常见运维案例、Runbook / SOP 和故障复盘模板，供团队维护与后续智能体检索复用。
        </Paragraph>
        <Space wrap>
          <Tag color="processing">本地 Markdown 存储</Tag>
          <Tag color="success">独立一级模块</Tag>
          <Tag color="gold">支持案例 / SOP / 模板</Tag>
        </Space>
      </Card>

      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card"><Statistic title="总条目" value={stats.total} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card"><Statistic title="运维案例" value={stats.case} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card"><Statistic title="Runbook / SOP" value={stats.runbook} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card"><Statistic title="复盘模板" value={stats.postmortem_template} /></Card>
        </Col>
      </Row>

      <Card className="module-card">
        <Tabs
          activeKey={filterType}
          onChange={(key) => setFilterType(key as KnowledgeEntryType)}
          items={[
            { key: 'case', label: '运维案例' },
            { key: 'runbook', label: 'Runbook / SOP' },
            { key: 'postmortem_template', label: '复盘模板' },
          ]}
        />
        <Space wrap style={{ marginBottom: 16 }}>
          <Input
            placeholder="搜索标题、摘要、服务、领域"
            value={filterQ}
            onChange={(e) => setFilterQ(e.target.value)}
            style={{ width: 280 }}
          />
          <Select
            allowClear
            showSearch
            placeholder="按标签筛选"
            value={filterTag || undefined}
            options={tagOptions}
            style={{ width: 220 }}
            onChange={(value) => setFilterTag(String(value || ''))}
          />
          <Button type="primary" onClick={() => void loadAll()} loading={loading}>
            查询
          </Button>
          <Button onClick={() => openCreate(filterType)}>新建{typeLabel[filterType]}</Button>
        </Space>

        <Table
          rowKey="id"
          columns={columns}
          dataSource={items}
          loading={loading}
          pagination={{ pageSize: 10, size: 'small' }}
          scroll={{ x: 1100, y: '52vh' }}
          locale={{ emptyText: '当前分类暂无知识条目，点击右上角新建。' }}
        />
      </Card>

      <Drawer
        title={drawerEntry ? `${typeLabel[drawerEntry.entry_type]}详情` : '详情'}
        width={720}
        open={Boolean(drawerEntry)}
        onClose={() => setDrawerEntry(null)}
      >
        {drawerEntry ? (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="标题" span={2}>{drawerEntry.title}</Descriptions.Item>
              <Descriptions.Item label="类型">{typeLabel[drawerEntry.entry_type]}</Descriptions.Item>
              <Descriptions.Item label="作者">{drawerEntry.author || '-'}</Descriptions.Item>
              <Descriptions.Item label="领域">{drawerEntry.domain || '-'}</Descriptions.Item>
              <Descriptions.Item label="聚合根">{drawerEntry.aggregate || '-'}</Descriptions.Item>
              <Descriptions.Item label="服务" span={2}>{joinTextList(drawerEntry.service_names)}</Descriptions.Item>
              <Descriptions.Item label="标签" span={2}>
                <Space wrap>{(drawerEntry.tags || []).map((tag) => <Tag key={tag}>{tag}</Tag>)}</Space>
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {formatBeijingDateTime(drawerEntry.created_at, '-')}
              </Descriptions.Item>
              <Descriptions.Item label="更新时间">
                {formatBeijingDateTime(drawerEntry.updated_at, '-')}
              </Descriptions.Item>
            </Descriptions>

            {drawerEntry.summary ? (
              <Card size="small" title="摘要">
                <Paragraph style={{ marginBottom: 0 }}>{drawerEntry.summary}</Paragraph>
              </Card>
            ) : null}

            {drawerEntry.entry_type === 'case' && drawerEntry.case_fields ? (
              <Card size="small" title="案例结构化信息">
                <Descriptions column={1} bordered size="small">
                  <Descriptions.Item label="故障类型">{drawerEntry.case_fields.incident_type || '-'}</Descriptions.Item>
                  <Descriptions.Item label="故障现象">{joinTextList(drawerEntry.case_fields.symptoms)}</Descriptions.Item>
                  <Descriptions.Item label="根因">{drawerEntry.case_fields.root_cause || '-'}</Descriptions.Item>
                  <Descriptions.Item label="解决方案">{drawerEntry.case_fields.solution || '-'}</Descriptions.Item>
                  <Descriptions.Item label="修复步骤">{joinTextList(drawerEntry.case_fields.fix_steps)}</Descriptions.Item>
                </Descriptions>
              </Card>
            ) : null}

            {drawerEntry.entry_type === 'runbook' && drawerEntry.runbook_fields ? (
              <Card size="small" title="Runbook / SOP 结构化信息">
                <Descriptions column={1} bordered size="small">
                  <Descriptions.Item label="适用场景">{joinTextList(drawerEntry.runbook_fields.applicable_scenarios)}</Descriptions.Item>
                  <Descriptions.Item label="执行前检查">{joinTextList(drawerEntry.runbook_fields.prechecks)}</Descriptions.Item>
                  <Descriptions.Item label="步骤">{joinTextList(drawerEntry.runbook_fields.steps)}</Descriptions.Item>
                  <Descriptions.Item label="回滚方案">{joinTextList(drawerEntry.runbook_fields.rollback_plan)}</Descriptions.Item>
                  <Descriptions.Item label="验证步骤">{joinTextList(drawerEntry.runbook_fields.verification_steps)}</Descriptions.Item>
                </Descriptions>
              </Card>
            ) : null}

            {drawerEntry.entry_type === 'postmortem_template' && drawerEntry.postmortem_fields ? (
              <Card size="small" title="复盘模板结构化信息">
                <Descriptions column={1} bordered size="small">
                  <Descriptions.Item label="影响面模板">{joinTextList(drawerEntry.postmortem_fields.impact_scope_template)}</Descriptions.Item>
                  <Descriptions.Item label="时间线模板">{joinTextList(drawerEntry.postmortem_fields.timeline_template)}</Descriptions.Item>
                  <Descriptions.Item label="5 Whys 模板">{joinTextList(drawerEntry.postmortem_fields.five_whys_template)}</Descriptions.Item>
                  <Descriptions.Item label="行动项模板">{joinTextList(drawerEntry.postmortem_fields.action_items_template)}</Descriptions.Item>
                </Descriptions>
              </Card>
            ) : null}

            <Card size="small" title="正文">
              <Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                {drawerEntry.content || '暂无正文'}
              </Paragraph>
            </Card>
          </Space>
        ) : null}
      </Drawer>

      <Modal
        title={editingEntry ? '编辑知识条目' : '新建知识条目'}
        open={modalOpen}
        width={860}
        onCancel={() => {
          setModalOpen(false);
          setEditingEntry(null);
          form.resetFields();
        }}
        onOk={() => void handleSave()}
        confirmLoading={saving}
        destroyOnClose
      >
        <Form form={form} layout="vertical" initialValues={emptyFormValues}>
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item label="类型" name="entry_type" rules={[{ required: true, message: '请选择类型' }]}>
                <Select
                  options={[
                    { label: '运维案例', value: 'case' },
                    { label: 'Runbook / SOP', value: 'runbook' },
                    { label: '复盘模板', value: 'postmortem_template' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={16}>
              <Form.Item label="标题" name="title" rules={[{ required: true, message: '请输入标题' }]}>
                <Input placeholder="请输入知识条目标题" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="摘要" name="summary">
            <TextArea rows={2} placeholder="一句话说明该条目的用途或结论" />
          </Form.Item>
          <Form.Item label="正文" name="content">
            <TextArea rows={6} placeholder="请输入正文内容，支持 markdown 文本" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}><Form.Item label="标签（逗号分隔）" name="tags_text"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item label="关联服务（逗号分隔）" name="service_names_text"><Input /></Form.Item></Col>
          </Row>
          <Row gutter={12}>
            <Col span={8}><Form.Item label="领域" name="domain"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item label="聚合根" name="aggregate"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item label="作者" name="author"><Input /></Form.Item></Col>
          </Row>

          {entryType === 'case' ? (
            <Card size="small" title="运维案例字段">
              <Row gutter={12}>
                <Col span={12}><Form.Item label="故障类型" name="case_incident_type"><Input /></Form.Item></Col>
                <Col span={12}><Form.Item label="故障现象（逗号分隔）" name="case_symptoms_text"><Input /></Form.Item></Col>
              </Row>
              <Form.Item label="根因" name="case_root_cause"><TextArea rows={2} /></Form.Item>
              <Form.Item label="解决方案" name="case_solution"><TextArea rows={2} /></Form.Item>
              <Form.Item label="修复步骤（逗号或换行分隔）" name="case_fix_steps_text"><TextArea rows={3} /></Form.Item>
            </Card>
          ) : null}

          {entryType === 'runbook' ? (
            <Card size="small" title="Runbook / SOP 字段">
              <Form.Item label="适用场景" name="runbook_applicable_text"><TextArea rows={2} /></Form.Item>
              <Form.Item label="执行前检查" name="runbook_prechecks_text"><TextArea rows={2} /></Form.Item>
              <Form.Item label="执行步骤" name="runbook_steps_text"><TextArea rows={3} /></Form.Item>
              <Form.Item label="回滚方案" name="runbook_rollback_text"><TextArea rows={2} /></Form.Item>
              <Form.Item label="验证步骤" name="runbook_verification_text"><TextArea rows={2} /></Form.Item>
            </Card>
          ) : null}

          {entryType === 'postmortem_template' ? (
            <Card size="small" title="复盘模板字段">
              <Form.Item label="影响面模板" name="postmortem_impact_text"><TextArea rows={2} /></Form.Item>
              <Form.Item label="时间线模板" name="postmortem_timeline_text"><TextArea rows={2} /></Form.Item>
              <Form.Item label="5 Whys 模板" name="postmortem_whys_text"><TextArea rows={2} /></Form.Item>
              <Form.Item label="行动项模板" name="postmortem_actions_text"><TextArea rows={2} /></Form.Item>
            </Card>
          ) : null}
        </Form>
      </Modal>
    </div>
  );
};

export default KnowledgePage;
