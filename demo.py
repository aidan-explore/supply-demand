import os
import pandas as pd
import datetime as dt
import streamlit as st
from pyairtable import Table
import logging

AIRTABLE_TOKEN = os.environ['AIRTABLE_TOKEN']
AIRTABLE_BASE_ID = "appTZVq2CZuxr4CoZ"

# REFACTOR: not needed as the data shouold not allow for many-to-many relationships
def get_first_list(input):
    if type(input) == str:
        return input
    elif type(input) == list:
        return input[0]
    
    return None

def get_relation_name(airtable : Table, field: str) -> dict:
    get_data = {k['id']: k['fields'][field] for k in airtable.all()}
    return get_data

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
def get_relations(df, table_name:str = "Roles", column_name:str = "Role"):
    
    air_table      = Table(AIRTABLE_TOKEN, AIRTABLE_BASE_ID, table_name)
    dict_lookups   = get_relation_name(air_table, column_name)
    df_lookups     = pd.DataFrame.from_dict(dict_lookups, orient="index", columns=[column_name + "_Name"])
    dict_relations = create_relations(df[column_name])
    
    df['_' + column_name] = df[column_name].apply(get_first_list)
    
    df = df.join(df_lookups, on='_' + column_name)
    
    return df, dict_lookups, dict_relations

@st.experimental_memo()
def get_requirements():
    
    mission_requirements = Table(AIRTABLE_TOKEN, AIRTABLE_BASE_ID, "Mission Requirements")
    
    require_fields = ['Requirement', 'Mission', 'Role', 'Seniority', 'Capacity', 'Client', '_start_date', '_end_date', '_prob']

    json_mission_requirements = {
        record['id'] : {k: v for k, v in record['fields'].items() if k in require_fields} 
        for record in mission_requirements.all()
        }

    df = pd.DataFrame.from_dict(json_mission_requirements, orient="index")

    return df

@st.experimental_memo()
def summarise_start_end(df: pd.DataFrame, freq = "1M", start_col: str = '_start_date', end_col: str = '_end_date') -> pd.DataFrame:
    
    df = df.reset_index()
        
    df['_start'] = pd.to_datetime(df[start_col].apply(get_first_list))
    df['_end']   = pd.to_datetime(df[end_col].apply(get_first_list))

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
              roles: list, groupby: str):
    date_mask = (data['Month_End'] >= pd.to_datetime(start_date)) & (data['Month_End'] <= pd.to_datetime(end_date))
    df = data[date_mask]
    
    if roles:    
        role_mask = df["Role_lookup"].isin(roles)
        df = df[role_mask]
    
    if groupby in df.columns:
        df_chart = df.pivot_table(columns=groupby, index='Month_End', values="Capacity", aggfunc="sum")
        
    else:
        df_chart = df.groupby(["Month_End"]).sum("Capacity")
        
    st.bar_chart(df_chart)
    
    st.dataframe(df[['Client_Name', "Mission_Name", "Role_Name", "Capacity"]].drop_duplicates())

st.set_page_config(
    page_title="ExploreAI Mission Requirements", page_icon="⬇", layout="centered"
)

st.image(image='eai.png',caption='https://explore.ai')

df = get_requirements()
df = summarise_start_end(df)
df, roles, role_dict       = get_relations(df, "Roles", "Role")
df, missions, mission_dict = get_relations(df, "Mission", "Mission")
df, clients, client_dict   = get_relations(df, "Clients", "Client")

st.title("⬇ Mission Requirements")
st.write("Number of people required by month")

# define the streamlit sidebar
choice_start   = st.sidebar.date_input('Select your start date:', value=pd.to_datetime('2022-04-01')) 
choice_end     = st.sidebar.date_input('Select your end date:', value=pd.to_datetime('2023-03-31')) 
choice_groupby = st.sidebar.radio('Select what to group by:', ('None', 'Seniority', "Role_Name", "Mission_Name", 'Client_Name')) 
choice_role    = st.sidebar.multiselect('Select your roles:', set([v for v in roles.values()]))
choice_client  = st.sidebar.multiselect('Select your Client:', set([v for v in clients.values()]), disabled=True)
choice_mission = st.sidebar.multiselect('Select your mission:', set([v for v in missions.values()]), disabled=True)
    
chart = get_chart(df, start_date=choice_start, end_date=choice_end, roles=choice_role, groupby=choice_groupby)

