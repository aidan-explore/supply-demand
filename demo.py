import os
import pandas as pd
import datetime as dt
import streamlit as st
from pyairtable import Table
import logging


# TODO: move to environment variables
AIRTABLE_TOKEN = os.environ['AIRTABLE_TOKEN']
AIRTABLE_BASE_ID = "appTZVq2CZuxr4CoZ"

def create_relations(input_series : pd.Series) -> dict:
    dict_relation = {}

    for _id, relation_list in input_series.items():
        if type(relation_list) != list:
            continue
        
        for relation in relation_list:
            if relation in dict_relation.keys():
                dict_relation[relation]['links'].append(_id)
            else:
                dict_relation[relation] = {'links' : [_id]}
                
    return dict_relation

def get_relation_name(dict_relation : dict, airtable : Table, field: str) -> dict:
    get_data = {k['id']: k['fields'][field] for k in airtable.all()}
    for k in dict_relation.keys():
        dict_relation[k]['name'] = get_data[k]
    
    return dict_relation

def get_first_list(input):
    if type(input) == str:
        return input
    elif type(input) == list:
        return input[0]
    
    return None

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

@st.experimental_memo()
def get_relations(df):
    
    roles       = Table(AIRTABLE_TOKEN, AIRTABLE_BASE_ID, "Roles")
    dict_roles  = create_relations(df["Role"])

    get_relation_name(dict_roles, roles, "Role")
    
    return df, dict_roles


# TODO: fix get_state error in caching this request
# @st.experimental_memo(ttl=60 * 60 * 24)
def get_chart(data, start_date: dt.datetime, end_date: dt.datetime, roles: list):
    date_mask = (data['Month_End'] >= pd.to_datetime(start_date)) & (data['Month_End'] <= pd.to_datetime(end_date))
    df = data[date_mask]
    
    # TODO: fix the role_mask
    # if roles:    
    #     role_mask = data["Role"].isin(roles)
    #     df = df[role_mask]
        
    return st.bar_chart(df, x="Month_End", y="Capacity")

st.set_page_config(
    page_title="ExploreAI Mission Requirements", page_icon="⬇", layout="centered"
)


df = get_requirements()
df = summarise_start_end(df)
df, role_dict = get_relations(df)


st.title("⬇ Mission Requirements")
st.write("Give more context to your time series using annotations!")

choice_start = st.sidebar.date_input('Select your start date:', value=pd.to_datetime('2022-04-01')) 
choice_end   = st.sidebar.date_input('Select your end date:', value=pd.to_datetime('2023-03-31')) 

choice_role  = st.sidebar.multiselect('Select your roles:', set([v['name'] for v in role_dict.values()]))
    
chart = get_chart(df, choice_start, choice_end, choice_role)

