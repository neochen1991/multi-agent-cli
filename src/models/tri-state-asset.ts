/**
 * 三态资产模型 - 运行态、开发态、设计态的统一建模
 * Tri-State Asset Model - Unified modeling of runtime, development, and design states
 */

import { z } from 'zod';

// ==================== 运行态资产 (Runtime Asset) ====================

/**
 * 异常信息
 */
export const ExceptionInfoSchema = z.object({
  type: z.string().describe('异常类型，如 NullPointerException'),
  message: z.string().describe('异常消息'),
  stackTrace: z.array(z.string()).describe('堆栈跟踪'),
  cause: z.string().optional().describe('根本原因异常'),
  timestamp: z.string().describe('异常发生时间'),
  threadName: z.string().optional().describe('线程名称'),
});

export type ExceptionInfo = z.infer<typeof ExceptionInfoSchema>;

/**
 * 线程信息
 */
export const ThreadInfoSchema = z.object({
  name: z.string().describe('线程名称'),
  state: z.enum(['NEW', 'RUNNABLE', 'BLOCKED', 'WAITING', 'TIMED_WAITING', 'TERMINATED']),
  priority: z.number().optional(),
  isDaemon: z.boolean().optional(),
  stackTrace: z.array(z.string()).optional(),
});

export type ThreadInfo = z.infer<typeof ThreadInfoSchema>;

/**
 * JVM 监控指标
 */
export const JVMMetricsSchema = z.object({
  heapUsed: z.number().describe('已用堆内存 (bytes)'),
  heapMax: z.number().describe('最大堆内存 (bytes)'),
  heapUsagePercent: z.number().describe('堆内存使用率'),
  gcCount: z.number().describe('GC 次数'),
  gcTime: z.number().describe('GC 总时间 (ms)'),
  threadCount: z.number().describe('线程数'),
  cpuUsage: z.number().optional().describe('CPU 使用率'),
  timestamp: z.string().describe('采集时间'),
});

export type JVMMetrics = z.infer<typeof JVMMetricsSchema>;

/**
 * Trace Span
 */
export const TraceSpanSchema = z.object({
  traceId: z.string().describe('追踪ID'),
  spanId: z.string().describe('Span ID'),
  parentSpanId: z.string().optional().describe('父 Span ID'),
  operationName: z.string().describe('操作名称'),
  startTime: z.number().describe('开始时间 (timestamp)'),
  duration: z.number().describe('持续时间 (ms)'),
  tags: z.record(z.string()).optional().describe('标签'),
  logs: z.array(z.object({
    timestamp: z.number(),
    fields: z.record(z.string()),
  })).optional().describe('日志'),
});

export type TraceSpan = z.infer<typeof TraceSpanSchema>;

/**
 * 慢 SQL
 */
export const SlowSQLSchema = z.object({
  sql: z.string().describe('SQL 语句'),
  executionTime: z.number().describe('执行时间 (ms)'),
  dataSource: z.string().optional().describe('数据源'),
  tableName: z.string().optional().describe('表名'),
  timestamp: z.string().describe('执行时间'),
  explainPlan: z.string().optional().describe('执行计划'),
});

export type SlowSQL = z.infer<typeof SlowSQLSchema>;

/**
 * HTTP 请求信息
 */
export const HttpRequestSchema = z.object({
  url: z.string().describe('请求 URL'),
  method: z.enum(['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']),
  headers: z.record(z.string()).optional(),
  queryParams: z.record(z.string()).optional(),
  requestBody: z.string().optional(),
  responseStatus: z.number().optional(),
  responseTime: z.number().optional().describe('响应时间 (ms)'),
});

export type HttpRequest = z.infer<typeof HttpRequestSchema>;

/**
 * 运行态资产
 */
export const RuntimeAssetSchema = z.object({
  // 异常信息
  exception: ExceptionInfoSchema.optional(),
  
  // HTTP 请求
  httpRequest: HttpRequestSchema.optional(),
  
  // 线程信息
  threadInfo: ThreadInfoSchema.optional(),
  
  // JVM 监控
  jvmMetrics: JVMMetricsSchema.optional(),
  
  // 链路追踪
  traces: z.array(TraceSpanSchema).optional(),
  
  // 慢 SQL
  slowSQLs: z.array(SlowSQLSchema).optional(),
  
  // 原始日志
  rawLogs: z.array(z.string()).optional(),
  
  // 时间戳
  timestamp: z.string().describe('资产采集时间'),
  
  // 来源标识
  source: z.object({
    serviceName: z.string().describe('服务名称'),
    instanceId: z.string().optional().describe('实例ID'),
    environment: z.enum(['development', 'staging', 'production']).optional(),
  }).describe('来源信息'),
});

export type RuntimeAsset = z.infer<typeof RuntimeAssetSchema>;

// ==================== 开发态资产 (Development Asset) ====================

/**
 * 聚合根信息
 */
export const AggregateRootSchema = z.object({
  name: z.string().describe('聚合根名称'),
  className: z.string().describe('类名'),
  packageName: z.string().describe('包名'),
  filePath: z.string().describe('文件路径'),
  methods: z.array(z.object({
    name: z.string(),
    returnType: z.string(),
    parameters: z.array(z.object({
      name: z.string(),
      type: z.string(),
    })),
    annotations: z.array(z.string()).optional(),
  })).optional(),
  annotations: z.array(z.string()).optional(),
});

export type AggregateRoot = z.infer<typeof AggregateRootSchema>;

/**
 * Controller 信息
 */
export const ControllerInfoSchema = z.object({
  className: z.string().describe('类名'),
  packageName: z.string().describe('包名'),
  basePath: z.string().optional().describe('基础路径'),
  filePath: z.string().describe('文件路径'),
  endpoints: z.array(z.object({
    path: z.string().describe('端点路径'),
    method: z.string().describe('HTTP 方法'),
    methodName: z.string().describe('方法名'),
    parameters: z.array(z.object({
      name: z.string(),
      type: z.string(),
      annotation: z.string().optional(),
    })).optional(),
    returnType: z.string().optional(),
    annotations: z.array(z.string()).optional(),
  })).describe('端点列表'),
});

export type ControllerInfo = z.infer<typeof ControllerInfoSchema>;

/**
 * Repository 信息
 */
export const RepositoryInfoSchema = z.object({
  name: z.string().describe('Repository 名称'),
  className: z.string().describe('类名'),
  packageName: z.string().describe('包名'),
  filePath: z.string().describe('文件路径'),
  entity: z.string().describe('关联实体'),
  methods: z.array(z.object({
    name: z.string(),
    returnType: z.string(),
    parameters: z.array(z.object({
      name: z.string(),
      type: z.string(),
    })),
    query: z.string().optional().describe('SQL 或 JPQL 查询'),
  })).optional(),
});

export type RepositoryInfo = z.infer<typeof RepositoryInfoSchema>;

/**
 * 数据库映射
 */
export const DBMappingSchema = z.object({
  tableName: z.string().describe('表名'),
  entityClass: z.string().describe('实体类'),
  columns: z.array(z.object({
    name: z.string(),
    type: z.string(),
    isPrimaryKey: z.boolean().optional(),
    isForeignKey: z.boolean().optional(),
    references: z.string().optional().describe('外键引用表'),
  })).describe('列信息'),
  indexes: z.array(z.object({
    name: z.string(),
    columns: z.array(z.string()),
    isUnique: z.boolean().optional(),
  })).optional(),
});

export type DBMapping = z.infer<typeof DBMappingSchema>;

/**
 * Git 仓库信息
 */
export const GitRepositorySchema = z.object({
  url: z.string().describe('仓库 URL'),
  branch: z.string().describe('当前分支'),
  commitHash: z.string().describe('当前提交哈希'),
  commitMessage: z.string().optional().describe('提交消息'),
  author: z.string().optional().describe('作者'),
  lastModified: z.string().optional().describe('最后修改时间'),
});

export type GitRepository = z.infer<typeof GitRepositorySchema>;

/**
 * 开发态资产
 */
export const DevelopmentAssetSchema = z.object({
  // Git 仓库信息
  repository: GitRepositorySchema.optional(),
  
  // 聚合根
  aggregateRoots: z.array(AggregateRootSchema).optional(),
  
  // Controllers
  controllers: z.array(ControllerInfoSchema).optional(),
  
  // Repositories
  repositories: z.array(RepositoryInfoSchema).optional(),
  
  // 数据库映射
  dbMappings: z.array(DBMappingSchema).optional(),
  
  // 服务类
  services: z.array(z.object({
    className: z.string(),
    packageName: z.string(),
    filePath: z.string(),
    annotations: z.array(z.string()).optional(),
  })).optional(),
  
  // 配置文件
  configurations: z.array(z.object({
    name: z.string(),
    path: z.string(),
    content: z.string().optional(),
  })).optional(),
});

export type DevelopmentAsset = z.infer<typeof DevelopmentAssetSchema>;

// ==================== 设计态资产 (Design Asset) ====================

/**
 * 领域模型
 */
export const DomainModelSchema = z.object({
  name: z.string().describe('领域名称'),
  description: z.string().optional().describe('领域描述'),
  boundedContext: z.string().optional().describe('限界上下文'),
  owner: z.string().optional().describe('责任田/负责人'),
  subdomains: z.array(z.string()).optional().describe('子域'),
});

export type DomainModel = z.infer<typeof DomainModelSchema>;

/**
 * 聚合设计
 */
export const AggregateSchema = z.object({
  name: z.string().describe('聚合名称'),
  aggregateRoot: z.string().describe('聚合根'),
  entities: z.array(z.string()).optional().describe('实体'),
  valueObjects: z.array(z.string()).optional().describe('值对象'),
  domainServices: z.array(z.string()).optional().describe('领域服务'),
  invariants: z.array(z.string()).optional().describe('不变性约束'),
  owner: z.string().optional().describe('负责人'),
});

export type Aggregate = z.infer<typeof AggregateSchema>;

/**
 * 接口设计
 */
export const InterfaceDesignSchema = z.object({
  name: z.string().describe('接口名称'),
  type: z.enum(['REST', 'RPC', 'MQ', 'EVENT']).describe('接口类型'),
  description: z.string().optional(),
  input: z.object({
    type: z.string(),
    fields: z.array(z.object({
      name: z.string(),
      type: z.string(),
      required: z.boolean().optional(),
      description: z.string().optional(),
    })).optional(),
  }).optional(),
  output: z.object({
    type: z.string(),
    fields: z.array(z.object({
      name: z.string(),
      type: z.string(),
      description: z.string().optional(),
    })).optional(),
  }).optional(),
  errorCodes: z.array(z.object({
    code: z.string(),
    message: z.string(),
    description: z.string().optional(),
  })).optional(),
});

export type InterfaceDesign = z.infer<typeof InterfaceDesignSchema>;

/**
 * 数据库表设计
 */
export const TableSchemaDesignSchema = z.object({
  tableName: z.string().describe('表名'),
  description: z.string().optional(),
  columns: z.array(z.object({
    name: z.string(),
    type: z.string(),
    nullable: z.boolean().optional(),
    defaultValue: z.string().optional(),
    comment: z.string().optional(),
  })),
  primaryKey: z.array(z.string()).describe('主键列'),
  foreignKeys: z.array(z.object({
    columns: z.array(z.string()),
    references: z.object({
      table: z.string(),
      columns: z.array(z.string()),
    }),
  })).optional(),
  indexes: z.array(z.object({
    name: z.string(),
    columns: z.array(z.string()),
    unique: z.boolean().optional(),
  })).optional(),
});

export type TableSchemaDesign = z.infer<typeof TableSchemaDesignSchema>;

/**
 * 历史案例引用
 */
export const CaseReferenceSchema = z.object({
  caseId: z.string().describe('案例ID'),
  title: z.string().describe('案例标题'),
  summary: z.string().describe('案例摘要'),
  rootCause: z.string().describe('根因'),
  solution: z.string().describe('解决方案'),
  similarity: z.number().min(0).max(1).optional().describe('相似度'),
  timestamp: z.string().describe('案例发生时间'),
});

export type CaseReference = z.infer<typeof CaseReferenceSchema>;

/**
 * 设计态资产
 */
export const DesignAssetSchema = z.object({
  // 领域模型
  domain: DomainModelSchema.optional(),
  
  // 聚合设计
  aggregates: z.array(AggregateSchema).optional(),
  
  // 接口设计
  interfaces: z.array(InterfaceDesignSchema).optional(),
  
  // 数据库表设计
  dbTables: z.array(TableSchemaDesignSchema).optional(),
  
  // 历史案例
  historicalCases: z.array(CaseReferenceSchema).optional(),
  
  // 架构决策记录
  adrs: z.array(z.object({
    id: z.string(),
    title: z.string(),
    status: z.enum(['proposed', 'accepted', 'deprecated', 'superseded']),
    date: z.string(),
    context: z.string(),
    decision: z.string(),
    consequences: z.string(),
  })).optional(),
  
  // 运维手册
  runbooks: z.array(z.object({
    name: z.string(),
    description: z.string(),
    steps: z.array(z.string()),
    triggers: z.array(z.string()).optional(),
  })).optional(),
});

export type DesignAsset = z.infer<typeof DesignAssetSchema>;

// ==================== 三态资产融合模型 ====================

/**
 * 三态资产融合模型
 */
export const TriStateAssetSchema = z.object({
  // 唯一标识
  incidentId: z.string().describe('故障/事件ID'),
  
  // 运行态
  runtime: RuntimeAssetSchema.describe('运行态资产'),
  
  // 开发态
  development: DevelopmentAssetSchema.optional().describe('开发态资产'),
  
  // 设计态
  design: DesignAssetSchema.optional().describe('设计态资产'),
  
  // 元数据
  metadata: z.object({
    createdAt: z.string().describe('创建时间'),
    updatedAt: z.string().describe('更新时间'),
    version: z.string().describe('版本'),
    collectedBy: z.string().optional().describe('采集者'),
  }).describe('元数据'),
});

export type TriStateAsset = z.infer<typeof TriStateAssetSchema>;

/**
 * 资产融合结果
 */
export const AssetFusionResultSchema = z.object({
  // 融合后的上下文
  context: z.string().describe('融合后的上下文描述'),
  
  // 关联关系
  relations: z.array(z.object({
    from: z.string().describe('来源资产'),
    to: z.string().describe('目标资产'),
    type: z.enum(['maps_to', 'references', 'implements', 'calls', 'depends_on']),
    confidence: z.number().min(0).max(1),
  })).describe('资产关联关系'),
  
  // 关键发现
  keyFindings: z.array(z.string()).describe('关键发现'),
  
  // 待补充资产
  missingAssets: z.array(z.object({
    type: z.enum(['runtime', 'development', 'design']),
    description: z.string(),
    priority: z.enum(['high', 'medium', 'low']),
  })).optional().describe('缺失的资产'),
});

export type AssetFusionResult = z.infer<typeof AssetFusionResultSchema>;
