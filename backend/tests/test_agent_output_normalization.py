"""test普通专家输出归一化相关测试。"""

from app.runtime.langgraph.parsers import normalize_agent_output


def test_normalize_agent_output_hoists_domain_analysis_payload():
    """验证普通专家归一化会抬平 domain_analysis 的结论、证据和置信度。"""

    raw = """```json
{
  "chat_message": "从领域视角看，事务边界明显越界。",
  "domain_analysis": {
    "interface_mapping": {
      "matched_domain": "order",
      "matched_aggregate": "OrderAggregate",
      "confidence": 0.99
    },
    "business_transaction_boundary": {
      "current_scope": "OrderAggregate#placeOrder",
      "violation_type": "事务边界过长——远程RPC同步调用内嵌事务",
      "problematic_dependencies": [
        {
          "service": "promotionClient",
          "method": "checkQuota",
          "evidence": "日志显示 cost=1847ms，阻塞事务"
        },
        {
          "service": "inventory",
          "method": "reservation update",
          "evidence": "update inventory_reservation 等待锁，txId=7812231"
        }
      ]
    },
    "root_cause_evidence": {
      "log_timestamp_chain": [
        "10:08:09 promotionClient.checkQuota cost=1847ms",
        "10:08:10 inventory lock wait txId=7812231",
        "10:08:11 HikariPool connection timeout"
      ],
      "causal_inference": "远程调用耗时1847ms -> 事务持有连接 -> 库存锁等待 -> 连接池耗尽"
    },
    "mapping_gaps": [
      "promotionClient 无明确责任田映射，需补全跨域调用规范"
    ],
    "next_checks": [
      "CodeAgent验证：promotionClient.checkQuota 是@FeignClient还是本地bean"
    ],
    "confidence": 0.85
  }
}
```"""

    payload = normalize_agent_output(
        "DomainAgent",
        raw,
        judge_fallback_summary="fallback",
    )

    assert payload["confidence"] == 0.85
    assert "事务边界过长" in payload["conclusion"]
    assert any("promotionClient.checkQuota cost=1847ms" in item["description"] for item in payload["evidence_chain"])
    assert any("promotionClient 无明确责任田映射" in item for item in payload["open_questions"])
    assert any("CodeAgent验证" in item for item in payload["needs_validation"])


def test_normalize_agent_output_hoists_analysis_result_payload():
    """验证普通专家归一化会兼容 analysis_result 形状的嵌套专家输出。"""

    raw = """```json
{
  "chat_message": "正在评估事务边界与业务规则匹配度。",
  "analysis_result": {
    "responsibility_mapping": {
      "matched": true,
      "confidence": 0.99,
      "domain": "order",
      "aggregate": "OrderAggregate"
    },
    "evidence": {
      "primary": [
        {
          "source": "log",
          "content": "promotionClient.checkQuota cost=1847ms sku=sku_10017",
          "interpretation": "远程RPC调用耗时1.8秒，阻塞事务"
        },
        {
          "source": "log",
          "content": "inventory reservation update waiting lock sku=sku_10017 txId=7812231",
          "interpretation": "库存预占因行锁等待，与促销校验同一事务"
        }
      ],
      "cross_validation": {
        "log_vs_code": "日志显示 checkQuota 在事务内，需 CodeAgent 确认 @Transactional 注解位置"
      }
    },
    "business_rules_assessment": {
      "sequencing_requirement": {
        "optimal": "库存预占（独立事务）→ 订单持久化 → 异步促销校验（后置补偿）",
        "confidence": 0.68
      }
    },
    "confidence": 0.71,
    "next_checks": [
      "CodeAgent 确认 @Transactional 注解在 placeOrder 方法的具体位置"
    ]
  }
}
```"""

    payload = normalize_agent_output(
        "DomainAgent",
        raw,
        judge_fallback_summary="fallback",
    )

    assert payload["confidence"] == 0.71
    assert "库存预占" in payload["conclusion"]
    assert any("promotionClient.checkQuota cost=1847ms" in item["description"] for item in payload["evidence_chain"])
    assert any("@Transactional 注解" in item for item in payload["needs_validation"])
