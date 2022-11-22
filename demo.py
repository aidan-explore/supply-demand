import datetime as dt
import os

import pandas as pd

import streamlit as st
import altair as alt

from pyairtable import Table

AIRTABLE_TOKEN = os.environ['AIRTABLE_TOKEN']
AIRTABLE_BASE_ID = "appTZVq2CZuxr4CoZ"

AIRTABLE_SCHEMA = {
    'Mission Requirements' : ['Requirement', 'Mission', 'Role', 'Seniority', 'Capacity', 'Client', "_renewal", '_start_date', '_end_date', '_prob', "Scenario"],
    'Mission Logs' : ['Client', 'Mission Log', 'Mission', 'Role', 'Seniority', 'EXPLORER', 'Capacity', "_prob", "_renewal", '_start_date', '_end_date', 'mission_requirement', "Scenario"]
}

def get_first_list(input):
    if type(input) == str:
        return input
    
    elif type(input) == list:
        return input[0]
    
    return input

@st.experimental_memo()
def get_relation_name(table_name: str, field: str) -> pd.DataFrame:
    airtable   = Table(AIRTABLE_TOKEN, AIRTABLE_BASE_ID, table_name)
    get_data   = {k['id']: k['fields'][field] for k in airtable.all()}
    df_lookups = pd.DataFrame.from_dict(get_data, orient="index", columns=[field + "_Name"])

    return df_lookups

@st.experimental_memo()
def create_relations(input_series : pd.Series) -> dict:
    dict_relation = {}

    for _id, relation_list in input_series.items():
        if type(relation_list) != list:
            continue
        
        for relation in relation_list:
            if relation in dict_relation.keys():
                dict_relation[relation].append(_id)
            else:
                dict_relation[relation] = [_id]
                
    return dict_relation

@st.experimental_memo()
def get_relations(df, df_lookups:pd.DataFrame, column_name:str):
    if column_name not in df.columns:
        return df, {}
    
    dict_relations        = create_relations(df[column_name])
    df['_' + column_name] = df[column_name].apply(get_first_list)
    df                    = df.join(df_lookups, on='_' + column_name)
    
    return df, dict_relations

@st.experimental_memo()
def get_requirements(table_name:str) -> pd.DataFrame:
    
    mission_requirements = Table(AIRTABLE_TOKEN, AIRTABLE_BASE_ID, table_name)
    require_fields       = AIRTABLE_SCHEMA[table_name]

    json_mission_requirements = {
        record['id'] : {k: v for k, v in record['fields'].items() if k in require_fields} 
        for record in mission_requirements.all()
        }

    df = pd.DataFrame.from_dict(json_mission_requirements, orient="index")

    return df

@st.experimental_memo()
def summarise_start_end(df: pd.DataFrame, freq = "1M", start_col: str = '_start_date', end_col: str = '_end_date', format='%Y-%m-%d') -> pd.DataFrame:
    
    df = df.reset_index()
        
    df['_start'] = pd.to_datetime(df[start_col].apply(get_first_list), format=format)
    df['_start'] = df['_start'].dt.date
    df['_end']   = pd.to_datetime(df[end_col].apply(get_first_list), format=format)
    df['_end']   = df['_end'].dt.date
    
    min_date = min(df['_start'].values)
    max_date = max(df['_end'].values)

    df_dates = pd.DataFrame([(i, end.replace(day=1), end) for i, end in enumerate(pd.date_range(start=min_date, end=max_date, freq=freq))], columns=['index', 'Month_Start', 'Month_End'])
    df_dates.set_index('index', inplace=True)

    df_temp = df.merge(df_dates, how='cross', indicator=True)
    
    df_temp['_capacity'] = df_temp['Capacity'].astype('float')
    df_temp.loc[df_temp['_start'] > df_temp['Month_Start'], '_capacity'] = 0.0
    df_temp.loc[df_temp['_end'] < df_temp['Month_End'], '_capacity'] = 0.0
    
    df_temp['_projected'] = df_temp['_capacity'] * df_temp['_probability']
    df_temp.loc[df_temp["Month_End"] > df_temp['_end'], '_projected'] = df_temp["Capacity"] * df_temp['_renewal']
        
    return df_temp

@st.experimental_memo()
def df_filter_dates(data: pd.DataFrame, start_date: dt.datetime, end_date: dt.datetime) -> pd.DataFrame:
    
    mask = (data['Month_End'] >= pd.to_datetime(start_date)) & (data['Month_End'] <= pd.to_datetime(end_date))
    df = data[mask]
    
    return df
    

@st.experimental_memo()
def df_filter_isin(data: pd.DataFrame, mask_dict:dict) -> pd.DataFrame:
    
    df = data
    
    for col_name, look_for in mask_dict.items():
        if col_name in df.columns:
            if look_for:
                mask = df[col_name].isin(look_for)
                df = df[mask]
                
    return df


def get_base_chart(data, groupby: str, values: str = "_capacity"):
    
    base = alt.Chart(data).encode(x="Month_End")
    bar = base.mark_bar(size=20).encode(y=f"sum({values})", color=f"{groupby}:O")
    
    return base, bar

def get_projected_chart(base: alt.Chart):
    
    line = base.mark_line(color='red').encode(y="sum(_prob_require)")
    line_projected = base.mark_line(color='red', strokeDash=[1, 5], ).encode(y="sum(_projected)")
    
    return line, line_projected

st.set_page_config(
    page_title="ExploreAI Mission Requirements", page_icon="⬇", layout="centered"
)

st.image(image='eai.png',caption='https://explore.ai')

roles     = get_relation_name("Roles", 'Role')
missions  = get_relation_name("Mission", "Mission")
clients   = get_relation_name("Clients", "Client")
explorers = get_relation_name("EXPLORER", "EXPLORER")
scenarios = get_relation_name("Scenarios", "Scenario")

# define the streamlit sidebar
choice_start    = st.sidebar.date_input('Select your start date:', value=pd.to_datetime('2022-04-01')) 
choice_end      = st.sidebar.date_input('Select your end date:', value=pd.to_datetime('2023-06-30')) 
choice_groupby  = st.sidebar.radio('Select what to group by:', ('None', 'Seniority', "Role_Name", "Mission_Name", 'Client_Name', "Scenario")) 
choice_role     = st.sidebar.multiselect('Select your Roles:', roles['Role_Name'].unique())
choice_client   = st.sidebar.multiselect('Select your Client:', clients['Client_Name'].unique())
choice_mission  = st.sidebar.multiselect('Select your Mission:', missions['Mission_Name'].unique())
choice_scenario = st.sidebar.multiselect('Select your Scenarios:', scenarios['Scenario_Name'].unique(), disabled=True)

requirements_filter = {
    "Role_Name" : choice_role,
    "Mission_Name" : choice_mission,
    "Client_Name" : choice_client,
    "Scenario_Name" : choice_scenario,
    }

tab_require, tab_allocate, tab_gap, tab_explorers, tab_data = st.tabs(["Requirements", "Allocations", "Gaps", "Explorers", "All Data"])

@st.experimental_memo(ttl=60 * 60 * 24)
def get_log_table(table_name:str):
    df = get_requirements(table_name)    
    
    link_dict = {}
    df, link_dict['Role']      = get_relations(df, roles, "Role")
    df, link_dict['Mission']   = get_relations(df, missions, "Mission")
    df, link_dict['Client']    = get_relations(df, clients, "Client")
    df, link_dict['Explorer']  = get_relations(df, explorers, "EXPLORER")
    df, link_dict['Scenarios'] = get_relations(df, scenarios, "Scenario")
    
    return df, link_dict

@st.experimental_memo()
def get_mission_requirements():
    
    df, _  = get_log_table('Mission Requirements')
    df     = df[df['Scenario'] != "9. Lost - 0%"]
    df['_probability'] = df['_prob'].apply(get_first_list)
    df['_probability'].fillna(0.0, inplace=True)
    df['_probability'] = df['_probability'].astype(float)
        
    df = summarise_start_end(df) 
    
    df['_prob_require'] = df['_capacity'] * df['_probability']
       
    return df

@st.experimental_memo()
def get_mission_logs():
    
    df, _  = get_log_table('Mission Logs')
    df['_requirement'] = df['mission_requirement'].apply(get_first_list)
    df = df[df["Scenario"] != "Rejected"]
    
    df['_probability'] = df['_prob'].apply(get_first_list)
    df['_probability'].fillna(0.0, inplace=True)
    df['_probability'] = df['_probability'].astype(float)
    
    df = summarise_start_end(df) 
    
    df_require = df.groupby(['_requirement', 'Month_End']).sum('_capacity')
    
    return df, df_require

# @st.experimental_memo()
def get_require_gaps(df_requirements: pd.DataFrame, df_require_logs: pd.DataFrame) -> pd.DataFrame:
    
    df_gaps = df_requirements.join(df_require_logs, on=['index', 'Month_End'], rsuffix="_logs")
    df_gaps['_capacity_logs'].fillna(0.0, inplace=True)
    df_gaps['Gap'] = df_gaps['_capacity'] - df_gaps['_capacity_logs']
    
    return df_gaps

@st.experimental_memo()
def get_explorer_allocations(df_mission_logs, explorers: pd.DataFrame):
    
    df = df_mission_logs[df_mission_logs['_capacity'] != 0]
    df.drop_duplicates(subset=["index", "_EXPLORER", "Month_End", 'Capacity'], inplace=True)
    
    df_explorers = df.groupby(["_EXPLORER", 'Month_End']).sum('_capacity')
    df_explorers.reset_index(inplace=True)
    df_explorers.set_index("_EXPLORER", inplace=True)
    df_explorers = explorers.join(df_explorers)
    df_explorers['_capacity'].fillna(0, inplace=True)
    df_explorers['Availability'] = df_explorers['_capacity'] - 1
    df_explorers['Month_End'] = df_explorers['Month_End'].dt.date
    
    return df_explorers

df_requirements = get_mission_requirements()
df_mission_logs, df_require_logs = get_mission_logs()
df_gaps = get_require_gaps(df_requirements, df_require_logs)
df_explorers = get_explorer_allocations(df_mission_logs, explorers)
    
with tab_data:
    st.write("Scenario Names")
    st.dataframe(scenarios)

    st.write("Requirements table")
    st.dataframe(df_requirements)
    
    st.write("Mission Logs")
    st.dataframe(df_mission_logs)
    
    st.write("add up requirements")
    st.dataframe(df_gaps)
    
    st.write("Explorers")
    st.dataframe(explorers)

with tab_require:
    st.title("Mission Requirements")
    st.write("Number of people required by month")
    
    df = df_filter_dates(df_requirements, start_date=choice_start, end_date=choice_end)
    df = df_filter_isin(df, requirements_filter)
    
    base, bar = get_base_chart(df, groupby=choice_groupby)
    line, projected = get_projected_chart(base)
    
    st.altair_chart((bar+line+projected), use_container_width=True)
    
    st.dataframe(df[['Client_Name', "Mission_Name", "Role_Name", 'Seniority', "Capacity"]].drop_duplicates())
    
with tab_allocate:
    st.title("Mission Logs")
    st.write("Number of people allocated by month")
    
    df = df_mission_logs[df_mission_logs['_capacity'] != 0.0]
    df = df_filter_dates(df, start_date=choice_start, end_date=choice_end)
    df = df_filter_isin(df, requirements_filter)
    
    base, bar = get_base_chart(df, groupby=choice_groupby)
    st.altair_chart(bar, use_container_width=True)
    
    st.dataframe(df[["Mission_Name", "Role_Name", 'EXPLORER_Name', "Capacity"]].drop_duplicates())

with tab_gap:
    st.title("Gaps in allocation")
    
    df = df_filter_dates(df_gaps, start_date=choice_start, end_date=choice_end)
    df = df_filter_isin(df, requirements_filter)
    
    base, bar = get_base_chart(df, groupby=choice_groupby, values="Gap")   
    
    df['_gap_prob'] = df['Gap'] * df['_probability']
    line = base.mark_line(color='red').encode(y='sum(_gap_prob)')
     
    st.altair_chart(bar + line, use_container_width=True)
        
    df = df[df['Gap'] != 0]
    df = df.drop_duplicates(subset = ["Mission_Name", "Role_Name", 'Seniority', "Capacity", 'Gap'])
    df = df[["Mission_Name", "Role_Name", 'Seniority', 'Month_End', "Capacity", 'Gap']]                        
    
    st.dataframe(df)
    
with tab_explorers:
    st.title("Explorer Allocations")
    st.write("Number of people allocated by month")
    st.write("not linked to filters on the left on left")
        
    show_not_allocated = st.checkbox("Show only Explorers not fully allocated")
    
    mask = (df_explorers['Month_End'] >= pd.to_datetime(choice_start)) & (df_explorers['Month_End'] <= pd.to_datetime(choice_end))
    df = df_explorers[mask]    
    
    base, bar = get_base_chart(df, groupby="Role_Name", values="Availability")
    st.altair_chart(bar, use_container_width=True)
    
    if show_not_allocated:
        df = df[df['Capacity'] != 1]
        
    df = df.pivot_table(index="EXPLORER_Name", columns="Month_End", values="Capacity", fill_value=0, aggfunc="sum")

    st.dataframe(df.drop_duplicates())


    

