import os
import pandas as pd
import datetime as dt
import streamlit as st
from pyairtable import Table
import logging

AIRTABLE_TOKEN = os.environ['AIRTABLE_TOKEN']
AIRTABLE_BASE_ID = "appTZVq2CZuxr4CoZ"

AIRTABLE_SCHEMA = {
    'Mission Requirements' : ['Requirement', 'Mission', 'Role', 'Seniority', 'Capacity', 'Client', '_start_date', '_end_date', '_prob', "Scenario"],
    'Mission Logs' : ['Client', 'Mission Log', 'Mission', 'Role', 'Seniority', 'EXPLORER', 'Capacity', '_start_date', '_end_date', 'mission_requirement', "Scenario"]
}

# REFACTOR: not needed as the data shouold not allow for many-to-many relationships
def get_first_list(input):
    if type(input) == str:
        return input
    elif type(input) == list:
        return input[0]
    
    return None

def get_relation_name(table_name: str, field: str) -> pd.DataFrame:
    airtable   = Table(AIRTABLE_TOKEN, AIRTABLE_BASE_ID, table_name)
    get_data   = {k['id']: k['fields'][field] for k in airtable.all()}
    df_lookups = pd.DataFrame.from_dict(get_data, orient="index", columns=[field + "_Name"])

    return df_lookups

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

    df_temp = df.merge(df_dates, how='cross')
    
    df_temp = df_temp[df_temp['_start'] <= df_temp['Month_Start']]
    df_temp = df_temp[df_temp['_end'] >= df_temp['Month_End']]
    
    return df_temp

# TODO: fix get_state error in caching this request
# @st.experimental_memo(ttl=60 * 60 * 24)
def get_chart(data, start_date: dt.datetime, end_date: dt.datetime, 
              roles: list, clients: list, missions:list,
              groupby: str, values: str = "Capacity"):
    mask = (data['Month_End'] >= pd.to_datetime(start_date)) & (data['Month_End'] <= pd.to_datetime(end_date))
    df = data[mask]
    
    if roles:    
        mask = df["Role_Name"].isin(roles)
        df = df[mask]
        
    if missions:
        mask = df['Mission_Name'].isin(missions)
        df = df[mask]
        
    if clients:
        mask = df['Client_Name'].isin(clients)
        df = df[mask]
    
    if groupby in df.columns:
        df_chart = df.pivot_table(columns=groupby, index='Month_End', values=values, aggfunc="sum")
        
    else:
        df_chart = df.groupby(["Month_End"]).sum(values)
        
    st.bar_chart(df_chart)
    
    return df

st.set_page_config(
    page_title="ExploreAI Mission Requirements", page_icon="⬇", layout="centered"
)

st.image(image='eai.png',caption='https://explore.ai')

roles     = get_relation_name("Roles", 'Role')
missions  = get_relation_name("Mission", "Mission")
clients   = get_relation_name("Clients", "Client")
explorers = get_relation_name("EXPLORER", "EXPLORER")
scenarios = get_relation_name("Scenarios", "Scenario")

def get_log_table(table_name:str):
    df = get_requirements(table_name)    
    df = summarise_start_end(df)
    
    link_dict = {}
    df, link_dict['Role']      = get_relations(df, roles, "Role")
    df, link_dict['Mission']   = get_relations(df, missions, "Mission")
    df, link_dict['Client']    = get_relations(df, clients, "Client")
    df, link_dict['Explorer']  = get_relations(df, explorers, "EXPLORER")
    df, link_dict['Scenarios'] = get_relations(df, scenarios, "Scenario")
    
    return df, link_dict

df_requirements, _  = get_log_table('Mission Requirements')
df_mission_logs, _  = get_log_table('Mission Logs')

df_requirements = df_requirements[df_requirements['Scenario'] != "9. Lost - 0%"]

df_mission_logs['_requirement'] = df_mission_logs['mission_requirement'].apply(get_first_list)
df_mission_logs = df_mission_logs[df_mission_logs["Scenario"] != "Rejected"]
df = df_mission_logs.groupby(['_requirement', 'Month_End']).sum('Capacity')
df.rename(columns={'Capacity' : 'Allocation'}, inplace=True)

df_gaps = df_requirements.join(df, on=['index', 'Month_End'])
df_gaps['Allocation'].fillna(0, inplace=True)
df_gaps['Gap'] = df_gaps['Capacity'] - df_gaps['Allocation']

df_explorers = df_mission_logs.groupby(["_EXPLORER", 'Month_End']).sum('Allocations')
df_explorers.reset_index(inplace=True)
df_explorers.set_index("_EXPLORER", inplace=True)
df_explorers = explorers.join(df_explorers)
df_explorers['Capacity'].fillna(0, inplace=True)
df_explorers['Availability'] = 1 - df_explorers['Capacity']
df_explorers['Month_End'] = df_explorers['Month_End'].dt.date

# define the streamlit sidebar
choice_start    = st.sidebar.date_input('Select your start date:', value=pd.to_datetime('2022-04-01')) 
choice_end      = st.sidebar.date_input('Select your end date:', value=pd.to_datetime('2023-03-31')) 
choice_groupby  = st.sidebar.radio('Select what to group by:', ('None', 'Seniority', "Role_Name", "Mission_Name", 'Client_Name', "Scenario")) 
choice_role     = st.sidebar.multiselect('Select your Roles:', roles['Role_Name'].unique())
choice_client   = st.sidebar.multiselect('Select your Client:', clients['Client_Name'].unique())
choice_mission  = st.sidebar.multiselect('Select your Mission:', missions['Mission_Name'].unique())
choice_scenario = st.sidebar.multiselect('Select your Scenarios:', scenarios['Scenario_Name'].unique(), disabled=True)

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Requirements", "Allocations", "Gaps", "Explorers", "All Data"])
    
with tab1:
    st.title("Mission Requirements")
    st.write("Number of people required by month")
    
    df = get_chart(df_requirements, start_date=choice_start, end_date=choice_end, 
                   roles=choice_role, clients=choice_client, missions=choice_mission, groupby=choice_groupby)
    st.dataframe(df[['Client_Name', "Mission_Name", "Role_Name", 'Seniority', "Capacity"]].drop_duplicates())
    
with tab2:
    st.title("Mission Logs")
    st.write("Number of people allocated by month")
    df = get_chart(df_mission_logs, start_date=choice_start, end_date=choice_end, 
                   roles=choice_role, clients=choice_client, missions=choice_mission, groupby=choice_groupby)
    st.dataframe(df[["Mission_Name", "Role_Name", 'EXPLORER_Name', "Capacity"]].drop_duplicates())

with tab3:
    st.title("Gaps in allocation")
    df = get_chart(df_gaps, start_date=choice_start, end_date=choice_end, 
                   roles=choice_role, clients=choice_client, missions=choice_mission, groupby=choice_groupby, values="Gap")
    
    df = df[df['Gap'] != 0]
    st.dataframe(df[["Mission_Name", "Role_Name", 'Seniority', 'Month_End', "Capacity", 'Allocation', 'Gap']].drop_duplicates())
    
with tab4:
    st.title("Explorer Allocations")
    st.write("Number of people allocated by month")
    st.write("not linked to filters on the left on left")
        
    show_not_allocated = st.checkbox("Show only Explorers not fully allocated")
    
    mask = (df_explorers['Month_End'] >= pd.to_datetime(choice_start)) & (df_explorers['Month_End'] <= pd.to_datetime(choice_end))
    df = df_explorers[mask]    
    
    if show_not_allocated:
        df = df[df['Capacity'] != 1]
        
    df = df.pivot_table(index="EXPLORER_Name", columns="Month_End", values="Capacity", fill_value=0, aggfunc="sum")

    st.dataframe(df.drop_duplicates())

    
with tab5:
    st.dataframe(scenarios)

    
    st.write("Requirements table")
    st.dataframe(df_requirements)
    
    st.write("Mission Logs")
    st.dataframe(df_mission_logs)
    
    st.write("add up requirements")
    st.dataframe(df_gaps)
    

