import pandas as pd
import numpy as np
import json
import logging
from typing import Dict, Optional, List, Tuple
from openai import OpenAI

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EnhancedQueryHandler:
    """Enhanced query handler for MOF database with context management and improved LLM usage."""
    
    IDENTIFIER_COLUMNS = ['CCDC_code', 'CCDC_number', 'Chemical_name', 'Synonyms']
    PROPERTY_COLUMNS = [
        'LCD (Å)', 
        'PLD (Å)', 
        'Density (g/cm3)',
        'Accessible_Surface_Area (m2/cm3)',
        'Accessible_Surface_Area (m2/g)',
        'Volume_Fraction'
    ]
    
    PROPERTY_ALIASES = {
        'surface area': ['Accessible_Surface_Area (m2/cm3)', 'Accessible_Surface_Area (m2/g)'],
        'density': ['Density (g/cm3)'],
        'lcd': ['LCD (Å)'],
        'pld': ['PLD (Å)'],
        'volume': ['Volume_Fraction'],
        'vsa': ['Accessible_Surface_Area (m2/cm3)'],
        'volumetric surface area': ['Accessible_Surface_Area (m2/cm3)'],
        'gsa': ['Accessible_Surface_Area (m2/g)'],
        'gravimetric surface area': ['Accessible_Surface_Area (m2/g)'],
        'name': ['Chemical_name', 'Synonyms'],
        'chemical name': ['Chemical_name', 'Synonyms'],
        'synonyms': ['Synonyms'],
        'ccdc number': ['CCDC_number'],
        'ccdc code': ['CCDC_code'],
    }

    def __init__(self, df: pd.DataFrame, openai_client: OpenAI):
        self.df = df
        self.client = openai_client
        self.context = {
            'last_query': None,
            'last_materials': [],
            'last_properties': [],
            'last_result': None,
            'paged_index': 0,
            'query_history': []
        }
        self._prepare_dataframe()

    def _prepare_dataframe(self):
        for col in self.PROPERTY_COLUMNS:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce')
        
        for col in self.IDENTIFIER_COLUMNS:
            if col in self.df.columns:
                if col == 'Synonyms':
                    self.df[f'{col}_list'] = (
                        self.df[col].fillna('').astype(str).str.split(';')
                    )
                    self.df[f'{col}_lower'] = self.df[col].fillna('').astype(str).str.lower()
                else:
                    self.df[f'{col}_lower'] = self.df[col].astype(str).str.lower()
        
        self._create_material_maps()
        logger.info(f"DataFrame prepared with {len(self.df)} rows")

    def _create_material_maps(self):
        """Create mapping dictionaries for quick material lookups."""
        self.material_maps = {}
        for col in self.IDENTIFIER_COLUMNS:
            if col == 'Synonyms':
                synonym_map = {}
                for idx, row in self.df.iterrows():
                    if pd.notna(row['Synonyms']):
                        synonyms = str(row['Synonyms']).lower().split(';')
                        for syn in synonyms:
                            syn = syn.strip()
                            if syn:
                                if syn not in synonym_map:
                                    synonym_map[syn] = []
                                synonym_map[syn].append(row['CCDC_code'])
                self.material_maps['Synonyms'] = synonym_map
            else:
                lower_col = f'{col}_lower'
                if lower_col in self.df.columns:
                    mapping = {}
                    for idx, val in self.df[lower_col].items():
                        code = self.df.loc[idx, 'CCDC_code']
                        if val not in mapping:
                            mapping[val] = []
                        mapping[val].append(code)
                    self.material_maps[col] = mapping

    def _find_material_ids(self, search_term: str) -> List[str]:
        """先做精确匹配，如无则做部分匹配."""
        term = search_term.lower().strip()
        exact = set()
        partial = set()

        for col, mapping in self.material_maps.items():
            if term in mapping:
                exact.update(mapping[term])

        if exact:
            return list(exact)

        for col, mapping in self.material_maps.items():
            for k, v in mapping.items():
                if term in k:
                    partial.update(v)

        return list(partial)

    def _resolve_properties(self, raw_props: List[str]) -> List[str]:
        resolved = []
        for p in raw_props:
            p_lower = p.lower().strip()
            if p_lower in self.PROPERTY_ALIASES:
                for col in self.PROPERTY_ALIASES[p_lower]:
                    if col in self.df.columns:
                        resolved.append(col)
            else:
                if p in self.df.columns:
                    resolved.append(p)
        return list(dict.fromkeys(resolved))

    def _analyze_query_with_llm(self, question: str, context_info: Dict) -> Optional[Dict]:
        system_message = {
            "role": "system",
            "content": (
                "You are an assistant for a MOF database. Parse the user's question into a JSON:\n"
                "{\n"
                '  "query_type": "chat"|"property"|"comparison"|"statistical"|"range"|"help"|"greeting"|"reset"|"unknown"|"paging",\n'
                '  "materials": [...],\n'
                '  "properties": [...],\n'
                '  "operation": {"type": "mean"|"max"|"min"|null, "value": null|float},\n'
                '  "range": {\n'
                '    "min": {"prop1": val1, "prop2": val2, ...},\n'
                '    "max": {"prop1": val1, "prop2": val2, ...}\n'
                '  },\n'
                '  "uses_context": bool,\n'
                '  "reasoning": [...],\n'
                '  "page_size": int|null\n'
                "}\n\n"
                "For range queries with multiple properties, parse ranges carefully including units.\n"
                "Examples:\n"
                "- 'PLD 7.5-10 Å, LCD 10-16 Å' =>\n"
                '"range": {"min":{"PLD":7.5,"LCD":10}, "max":{"PLD":10,"LCD":16}}\n'
                "- 'VSA 2000-2400 m2/cm3, density 0.8-1.2 g/cm3' =>\n"
                '"range": {"min":{"VSA":2000,"density":0.8}, "max":{"VSA":2400,"density":1.2}}\n'
                "Always include proper units in property names"
            )
        }
        user_message = {
            "role": "user",
            "content": f"User question: {question}\n\nContext info:\n{json.dumps(context_info, indent=2)}"
        }
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini-2024-07-18",
                messages=[system_message, user_message],
                temperature=0.0
            )
            raw_content = response.choices[0].message.content.strip()
            return json.loads(raw_content)
        except Exception as e:
            logger.error(f"LLM parse error: {e}")
            return None

    def _fallback_llm_parse(self, question: str, context_info: Dict) -> Optional[Dict]:
        """更严格的 function calling, 支持多property range查询."""
        schema = {
            "name": "parse_mof_query",
            "description": "Parse user MOF query into structured JSON with multiple property ranges.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "description": "One of [chat, property, comparison, statistical, range, help, greeting, reset, unknown, paging]."
                    },
                    "materials": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "properties": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "operation": {
                        "type": "object",
                        "properties": {
                            "type": {"type":["string","null"]},
                            "value": {"type":["number","null"]}
                        },
                        "required": ["type","value"]
                    },
                    "range": {
                        "type": "object",
                        "description": "A dict of {min:{prop:val}, max:{prop:val}}",
                        "properties": {
                            "min": {
                                "type": "object",
                                "additionalProperties": {"type": "number"}
                            },
                            "max": {
                                "type": "object",
                                "additionalProperties": {"type": "number"}
                            }
                        }
                    },
                    "uses_context": {"type":"boolean"},
                    "reasoning": {
                        "type":"array",
                        "items":{"type":"string"}
                    },
                    "page_size": {"type":["integer","null"]}
                },
                "required": ["query_type","materials","properties","operation","range","uses_context","reasoning","page_size"]
            }
        }
        
        system_msg = {
            "role":"system",
            "content": (
                "You are a MOF query parser. Parse queries with multi-property ranges. "
                "Examples:\n"
                "- 'PLD 7.5-10 Å, LCD 10-16 Å' => range:{min:{PLD:7.5,LCD:10}, max:{PLD:10,LCD:16}}\n"
                "- 'VSA 2000-2400 m2/cm3' => range:{min:{VSA:2000}, max:{VSA:2400}}\n"
                "If user says 'help' => query_type='help'."
            )
        }
        
        user_msg = {
            "role":"user", 
            "content": f"Question: {question}\nContext: {json.dumps(context_info,indent=2)}"
        }

        try:
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini-2024-07-18",
                messages=[system_msg, user_msg],
                functions=[schema],
                function_call={"name":"parse_mof_query"},
                temperature=0.0
            )
            choice = resp.choices[0].message
            if "function_call" in choice:
                arg_str = choice.function_call.arguments
                return json.loads(arg_str)
            return None
        except Exception as e:
            logger.error(f"Fallback LLM parse error: {e}")
            return None

    def _analyze_query(self, question:str)->Dict:
        context_info = {
            'last_query': self.context['last_query'],
            'last_materials': self.context['last_materials'][-3:],
            'last_properties': self.context['last_properties'][-3:]
        }
        
        q_lower = question.lower().strip()
        if q_lower in ["help","what can you do"]:
            return {
                "query_type":"help",
                "materials":[],
                "properties":[],
                "operation":{"type":None,"value":None},
                "range":{},
                "uses_context":False,
                "reasoning":[],
                "page_size":None
            }

        analysis = self._analyze_query_with_llm(question, context_info)
        if not analysis:
            logger.warning("LLM analysis failed => trying fallback parse")
            analysis = self._fallback_llm_parse(question, context_info)
            
        if not analysis:
            logger.warning("All parsing attempts failed => fallback to chat")
            return {
                "query_type":"chat",
                "materials":[],
                "properties":[],
                "operation":{"type":None,"value":None},
                "range":{},
                "uses_context":False,
                "reasoning":[],
                "page_size":None
            }

        required = ["query_type","materials","properties","operation","range","uses_context","reasoning","page_size"]
        for r in required:
            if r not in analysis:
                analysis[r] = {} if r=="range" else None if r=="page_size" else []

        if not analysis["operation"]:
            analysis["operation"]={"type":None,"value":None}
        if not analysis["range"]:
            analysis["range"]={}

        return analysis

    def get_query_data(self, analysis: Dict)->pd.DataFrame:
        try:
            materials = analysis.get('materials',[])
            uses_ctx = analysis.get('uses_context',False)
            if not materials and uses_ctx and self.context["last_materials"]:
                materials = self.context["last_materials"]

            raw_props = analysis.get('properties',[])
            qtype = analysis.get('query_type')
            if not raw_props and qtype=="comparison":
                raw_props = self.IDENTIFIER_COLUMNS + self.PROPERTY_COLUMNS
            if not raw_props and qtype in ["chat","unknown","help","comparison"]:
                raw_props = self.IDENTIFIER_COLUMNS + self.PROPERTY_COLUMNS

            resolved_props = self._resolve_properties(raw_props)
            if not resolved_props and qtype=="property":
                resolved_props = self.IDENTIFIER_COLUMNS + self.PROPERTY_COLUMNS

            needed_cols = ["CCDC_code"]
            for c in resolved_props:
                if c in self.df.columns and c not in needed_cols:
                    needed_cols.append(c)

            query_df = self.df[needed_cols].copy()

            if materials:
                mask = pd.Series(False, index=query_df.index)
                for m in materials:
                    codes = self._find_material_ids(m)
                    if codes:
                        mask |= self.df["CCDC_code"].isin(codes)
                query_df = query_df[mask]

            # Use all property aliases for mapping
            property_map = {}
            for alias, columns in self.PROPERTY_ALIASES.items():
                for col in columns:
                    if col in self.df.columns:
                        property_map[alias] = col
                        property_map[alias.upper()] = col

            # 范围过滤
            range_info = analysis.get('range', {})
            min_dict = range_info.get('min', {})
            max_dict = range_info.get('max', {})

            # 处理最小值过滤
            for prop_name, min_val in min_dict.items():
                try:
                    if prop_name in query_df.columns:
                        query_df = query_df[query_df[prop_name] >= min_val]
                        continue
                        
                    resolved_name = property_map.get(prop_name.lower(), prop_name)
                    resolved_props = self._resolve_properties([resolved_name])
                    
                    if resolved_props:
                        col = resolved_props[0]
                        if col in query_df.columns:
                            query_df = query_df[query_df[col] >= min_val]
                    else:
                        logger.warning(f"Could not resolve property: {prop_name}")
                except Exception as e:
                    logger.error(f"Error filtering {prop_name}: {e}")

            # 处理最大值过滤
            for prop_name, max_val in max_dict.items():
                try:
                    if prop_name in query_df.columns:
                        query_df = query_df[query_df[prop_name] <= max_val]
                        continue
                        
                    resolved_name = property_map.get(prop_name.lower(), prop_name)
                    resolved_props = self._resolve_properties([resolved_name])
                    
                    if resolved_props:
                        col = resolved_props[0]
                        if col in query_df.columns:
                            query_df = query_df[query_df[col] <= max_val]
                    else:
                        logger.warning(f"Could not resolve property: {prop_name}")
                except Exception as e:
                    logger.error(f"Error filtering {prop_name}: {e}")

            # 统计操作
            operation = analysis.get('operation', {})
            op_type = operation.get('type')
            if op_type in ['mean', 'max', 'min'] and resolved_props:
                if op_type == 'mean':
                    means = query_df[resolved_props].mean(numeric_only=True)
                    row_dict = {col: means[col] for col in means.index if pd.notna(means[col])}
                    row_dict["CCDC_code"] = "AVERAGE"
                    query_df = pd.DataFrame([row_dict], columns=needed_cols)
                elif op_type == 'max':
                    prop = resolved_props[0]
                    if prop in query_df.columns and not query_df.empty:
                        idx = query_df[prop].idxmax()
                        query_df = query_df.loc[[idx]]
                    else:
                        query_df = pd.DataFrame(columns=needed_cols)
                elif op_type == 'min':
                    prop = resolved_props[0]
                    if prop in query_df.columns and not query_df.empty:
                        idx = query_df[prop].idxmin()
                        query_df = query_df.loc[[idx]]
                    else:
                        query_df = pd.DataFrame(columns=needed_cols)

            return query_df
        except Exception as e:
            logger.error(f"Data retrieval error: {e}")
            return pd.DataFrame()

    def _format_response_with_llm(self, question: str, df: pd.DataFrame, analysis: Dict) -> str:
        try:
            if df.empty:
                return "No matching data found."

            max_rows = 5
            truncated = df.head(max_rows)
            data_records = truncated.to_dict(orient='records')

            system_msg = {
                "role": "system",
                "content": (
                    "You are a MOF database assistant. Provide a concise helpful answer."
                )
            }
            user_msg = {
                "role": "user",
                "content": f"""
User question: {question}

Analysis:
{json.dumps(analysis, indent=2)}

Results (up to {max_rows}):
{json.dumps(data_records, indent=2)}
"""
            }
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini-2024-07-18",
                messages=[system_msg, user_msg],
                temperature=0.3
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Response formatting error: {e}")
            return self._format_fallback_response(df)

    def _format_fallback_response(self, df: pd.DataFrame) -> str:
        if df.empty:
            return "No matching data found."
        return df.head(5).to_string()

    def _format_paging_response(self, page_df: pd.DataFrame, remaining: int) -> str:
        if page_df.empty:
            return "No more data available."
        lines = ["Here are the next results:\n"]
        for idx, row in page_df.iterrows():
            lineinfo = [f"{col}: {row[col]}" for col in row.index]
            lines.append("  - " + ", ".join(lineinfo))
        if remaining > 0:
            lines.append("\nThere are more rows remaining, say 'give me another X' to see more.")
        return "\n".join(lines)

    def _update_context(self, question: str, analysis: Dict, result_df: pd.DataFrame):
        self.context['last_query'] = question
        if analysis['query_type'] == 'reset':
            self.reset_context()
            return
        if analysis['query_type'] != 'paging':
            self.context['paged_index'] = 0
            self.context['last_result'] = result_df
        if not result_df.empty and 'CCDC_code' in result_df.columns:
            ccdc_list = list(result_df['CCDC_code'].unique())
            self.context['last_materials'] = ccdc_list

        rawp = analysis.get('properties', [])
        rp = self._resolve_properties(rawp)
        if rp:
            self.context['last_properties'] = rp

        self.context['query_history'].append({
            'question': question,
            'analysis': analysis,
            'materials': self.context['last_materials'],
            'properties': self.context['last_properties']
        })
        if len(self.context['query_history']) > 10:
            self.context['query_history'] = self.context['query_history'][-10:]

    def process_query(self, question: str) -> str:
        try:
            analysis = self._analyze_query(question)
            if not analysis:
                return "I couldn't process that query. Could you rephrase it?"

            logger.info(f"Query analysis: {analysis}")

            if analysis['query_type'] == 'paging':
                pgsize = analysis.get('page_size') or 5
                fulldf = self.context['last_result']
                if fulldf is None or fulldf.empty:
                    return "No previous data to paginate."

                startidx = self.context['paged_index']
                endidx = startidx + pgsize
                page_df = fulldf.iloc[startidx:endidx]
                self.context['paged_index'] = endidx
                remain = max(0, len(fulldf) - endidx)
                response = self._format_paging_response(page_df, remain)
                self._update_context(question, analysis, page_df)
                return response

            result_df = self.get_query_data(analysis)
            if result_df.empty and analysis.get('uses_context'):
                analysis['uses_context'] = False
                result_df = self.get_query_data(analysis)

            final_answer = self._final_decision_with_llm(question, analysis, result_df)

            if '"reset_context": true' in final_answer.lower():
                self.reset_context()
                return "Context has been reset.\n" + final_answer
            if analysis['query_type'] == 'reset':
                self.reset_context()
                return "Context has been reset. How can I help you next?"

            self._update_context(question, analysis, result_df)
            return final_answer

        except Exception as e:
            logger.error(f"Query processing error: {e}")
            return f"Error processing query: {e}. Please try rephrasing."

    def _final_decision_with_llm(self, question: str, analysis: Dict, df: pd.DataFrame) -> str:
        try:
            if df.empty:
                return "No matching data found."

            max_rows = 5
            truncated = df.head(max_rows)
            data_records = truncated.to_dict(orient='records')

            extra_instr = ""
            if analysis['query_type'] == 'comparison':
                rawp = analysis.get('properties', [])
                if not rawp:
                    extra_instr = "Show all columns in a readable manner.\n"

            system_msg = {
                "role": "system",
                "content": (
                    "You are a MOF database assistant. Provide final answer.\n"
                    "If multiple rows, show them briefly. If user wants more, they can request pagination.\n"
                    + extra_instr
                )
            }
            user_msg = {
                "role": "user",
                "content": f"""
User's question: {question}

Analysis:
{json.dumps(analysis, indent=2)}

DataFrame (up to {max_rows} rows):
{json.dumps(data_records, indent=2)}
"""
            }
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini-2024-07-18",
                messages=[system_msg, user_msg],
                temperature=0.2
            )
            return resp.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Final decision LLM error: {e}")
            if df.empty:
                return "No matching data found. (Fallback due to error.)"
            return df.head(5).to_string() + "\n(Fallback output.)"

    def reset_context(self):
        self.context = {
            'last_query': None,
            'last_materials': [],
            'last_properties': [],
            'last_result': None,
            'paged_index': 0,
            'query_history': []
        }
        logger.info("Context reset")

    def get_available_properties(self) -> List[str]:
        return self.PROPERTY_COLUMNS

    def __str__(self) -> str:
        return (f"MOF Query Handler\n"
                f"Materials: {len(self.df)}\n"
                f"Properties: {len(self.PROPERTY_COLUMNS)}\n"
                f"Context depth: {len(self.context['query_history'])}")