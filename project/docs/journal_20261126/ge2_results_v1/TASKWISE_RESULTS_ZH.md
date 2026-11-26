# GE2 37个实际终局逐格核对

P/F/U是原自由回复合同的助手开发完成区间，不是正式reward。F不等同事实编造，U不计为0。所有37格均实际执行、EOS非空；无length、fallback或未执行。时间是本地单调钟实测，未测客户端/有效语音。

来源列是必要原子供应，G03的未知与自然支持无必答历史分别标记；覆盖不是成功。G输入/输出仅终局，全部输入/输出包含控制调用。PM/工具/守卫包含于在线时间，不能重复相加。原始文本与逐字私人审阅见复跑说明指向的本机完整报告。

|题|条件|完成|必要供应|G输入/输出token|全部调用输入/输出|完整秒|Agent至G内部首文字秒|PM秒|控制调用|实际获取|停止原因|
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
|G01|STOP|F|0/2|80/77|80/77|6.653|0.965|0.284|0|无|fixed_no_acquisition|
|G01|FixedTop4|P|2/2|3744/38|3744/38|5.604|2.785|0.978|0|SEARCH→EXPAND→EXPAND→EXPAND→EXPAND|fixed_program_complete|
|G01|LLMOneShot|P|2/2|848/48|1873/108|9.920|6.288|5.744|1|SEARCH|oneshot_program_end|
|G01|LLMToolAgent|P|2/2|848/48|4576/182|16.504|12.932|12.412|2|SEARCH|model_active_stop|
|G01|DirectEvidence|P|2/2|305/53|305/53|4.626|0.603|0.225|0|无|direct_evidence_diagnostic_no_policy|
|G02|STOP|F|0/2|80/71|80/71|5.894|0.594|0.284|0|无|fixed_no_acquisition|
|G02|FixedTop4|U|2/2|3509/55|3509/55|6.729|2.655|0.978|0|SEARCH→EXPAND→EXPAND→EXPAND→EXPAND|fixed_program_complete|
|G02|LLMOneShot|F|0/2|891/76|1914/129|11.529|5.843|5.302|1|SEARCH|oneshot_program_end|
|G02|LLMToolAgent|F|2/2|900/31|4667/179|16.396|14.054|13.462|2|SEARCH|model_active_stop|
|G02|DirectEvidence|U|2/2|331/51|331/51|4.418|0.599|0.225|0|无|direct_evidence_diagnostic_no_policy|
|G03|STOP|P|未知|81/74|81/74|6.544|0.994|0.301|0|无|fixed_no_acquisition|
|G03|FixedTop4|P|未知|3729/94|3729/94|9.796|2.852|1.028|0|SEARCH→EXPAND→EXPAND→EXPAND→EXPAND|fixed_program_complete|
|G03|LLMOneShot|P|未知|925/74|1950/131|11.679|6.119|5.528|1|SEARCH|oneshot_program_end|
|G03|LLMToolAgent|P|未知|943/71|4762/194|17.830|12.476|11.904|2|SEARCH|model_active_stop|
|G03|DirectEvidence|P|未知|656/95|656/95|8.012|0.675|0.225|0|无|direct_evidence_diagnostic_no_policy|
|G04|STOP|U|无必答历史|121/51|121/51|4.535|0.570|0.251|0|无|fixed_no_acquisition|
|G04|FixedTop4|U|无必答历史|4036/40|4036/40|5.946|2.921|0.945|0|SEARCH→EXPAND→EXPAND→EXPAND→EXPAND|fixed_program_complete|
|G04|LLMOneShot|U|无必答历史|121/51|1258/100|8.962|5.074|4.743|1|无|model_active_stop|
|G04|LLMToolAgent|P|无必答历史|997/46|5028/162|15.839|12.351|11.704|2|SEARCH|model_active_stop|
|G05|STOP|P|无必答历史|91/52|91/52|5.111|1.177|0.301|0|无|fixed_no_acquisition|
|G05|FixedTop4|P|无必答历史|4550/34|4550/34|5.796|3.210|0.945|0|SEARCH→EXPAND→EXPAND→EXPAND→EXPAND|fixed_program_complete|
|G05|LLMOneShot|P|无必答历史|91/52|1149/92|8.045|4.171|3.886|1|无|model_active_stop|
|G05|LLMToolAgent|P|无必答历史|954/40|4829/159|15.013|12.010|11.471|2|SEARCH|model_active_stop|
|G06|STOP|P|无必答历史|93/44|93/44|3.794|0.491|0.217|0|无|fixed_no_acquisition|
|G06|FixedTop4|P|无必答历史|3513/42|3513/42|5.604|2.479|0.853|0|SEARCH→EXPAND→EXPAND→EXPAND→EXPAND|fixed_program_complete|
|G06|LLMOneShot|P|无必答历史|93/44|1146/87|7.753|4.428|4.126|1|无|model_active_stop|
|G06|LLMToolAgent|P|无必答历史|93/44|1121/88|7.745|4.461|4.160|1|无|model_active_stop|
|G07|STOP|F|1/2|142/79|142/79|6.778|0.941|0.251|0|无|fixed_no_acquisition|
|G07|FixedTop4|P|2/2|4194/66|4194/66|7.871|2.987|1.003|0|SEARCH→EXPAND→EXPAND→EXPAND→EXPAND|fixed_program_complete|
|G07|LLMOneShot|F|1/2|953/62|2164/117|10.446|5.817|5.236|1|SEARCH|oneshot_program_end|
|G07|LLMToolAgent|F|1/2|953/62|5048/186|17.005|12.393|11.804|2|SEARCH|model_active_stop|
|G07|DirectEvidence|P|2/2|398/49|398/49|4.177|0.539|0.159|0|无|direct_evidence_diagnostic_no_policy|
|G08|STOP|U|2/2|132/65|132/65|5.385|0.560|0.242|0|无|fixed_no_acquisition|
|G08|FixedTop4|P|2/2|3942/50|3942/50|6.571|2.893|0.987|0|SEARCH→EXPAND→EXPAND→EXPAND→EXPAND|fixed_program_complete|
|G08|LLMOneShot|U|2/2|132/65|1307/123|10.379|5.536|5.219|1|无|model_active_stop|
|G08|LLMToolAgent|U|2/2|132/65|1288/126|10.478|5.636|5.352|1|无|model_active_stop|
|G08|DirectEvidence|P|2/2|348/50|348/50|4.277|0.560|0.167|0|无|direct_evidence_diagnostic_no_policy|

全部毫秒以下精度、语义分项与成本组件见 [37格JSONL](ENDPOINTS_REVIEWED_PUBLIC.jsonl)；配对变化见 [48行配对表](PAIRED_TASKWISE_PUBLIC.jsonl)。完整解释见 [主报告](GE2_ACTUAL_RESULTS_AND_DECISIONS_ZH.md)。
