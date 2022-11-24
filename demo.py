import datetime as dt
import os

import pandas as pd

import streamlit as st
import altair as alt

from pyairtable import Table

AIRTABLE_TOKEN = os.environ['AIRTABLE_TOKEN']
AIRTABLE_BASE_ID = "appTZVq2CZuxr4CoZ"

AIRTABLE_SCHEMA = {
    'Mission Requirements' : ['Requirement', 'Mission', 'Role', 'Seniority', 'Capacity', 'Client', "_prob", "_renewal", '_start_date', '_end_date', '_end_mission', "Scenario"],
    'Mission Logs' : ['Mission Log', 'Client', 'Mission', 'Role', 'Seniority', 'EXPLORER', 'Capacity', "_prob", "_renewal", '_start_date', '_end_date', 'mission_requirement', "Scenario", "State"],
    'EXPLORER' : ['EXPLORER', 'Role', 'Belt Colour', 'Start Date', 'End Date', 'Active'],
    'Roles' : ['Role', 'Capability'],
    'Scenarios' : ['Scenario', 'Probability'],
    "Clients" : ['Client', 'Status'],
    "Mission" : ['Mission', 'Start Date', 'End Date', 'Scenario', 'Renewal']
}

# helper code
@st.experimental_memo()
def convert_df(df):
   return df.to_csv(index=False).encode('utf-8')

def get_first_list(input):
    if type(input) == str:
        return input
    
    elif type(input) == list:
        return input[0]
    
    return input

# ingestions nodes
def get_raw_airtable(airtable_token: str, airtable_base: str, air_tablename: str) -> pd.DataFrame:
    
    json = Table(airtable_token, airtable_base, air_tablename).all()
    df   = pd.json_normalize(json)
    df.set_index('id', inplace=True)
    df.rename(columns={col: col.replace('fields.', '') for col in df.columns}, inplace=True)
    df = df[AIRTABLE_SCHEMA[air_tablename]]
    
    return df

def air_join(left_df: pd.DataFrame, right_df: pd.DataFrame, left_on: str, right_name: str = None) -> pd.DataFrame:
    
    if not right_name:
        right_name = left_on

    left_df[left_on] = left_df[left_on].apply(get_first_list)   
    return left_df.join(right_df[right_name], on=left_on, rsuffix="_Name")

@st.experimental_memo()
def get_raw_data():

    roles     = get_raw_airtable(AIRTABLE_TOKEN, AIRTABLE_BASE_ID, "Roles")
    missions  = get_raw_airtable(AIRTABLE_TOKEN, AIRTABLE_BASE_ID, "Mission")
    clients   = get_raw_airtable(AIRTABLE_TOKEN, AIRTABLE_BASE_ID, "Clients")
    explorers = get_raw_airtable(AIRTABLE_TOKEN, AIRTABLE_BASE_ID, "EXPLORER")
    scenarios = get_raw_airtable(AIRTABLE_TOKEN, AIRTABLE_BASE_ID, "Scenarios")

    requirements = get_raw_airtable(AIRTABLE_TOKEN, AIRTABLE_BASE_ID, "Mission Requirements")
    logs         = get_raw_airtable(AIRTABLE_TOKEN, AIRTABLE_BASE_ID, "Mission Logs")
    
    explorers = air_join(explorers, roles, "Role") 
    
    return roles, missions, clients, explorers, scenarios, requirements, logs

@st.experimental_memo()
def get_mission_requirements(df_require: pd.DataFrame) -> pd.DataFrame:
    
    df = air_join(df_require, roles, "Role")
    df = air_join(df, missions, "Mission")
    df = air_join(df, clients, "Client")
    df = air_join(df, scenarios, "Scenario")
        
    df  = df[df['Scenario'] != "9. Lost - 0%"]
    
    df['_probability'] = df['_prob'].apply(get_first_list)
    df['_probability'].fillna(0.0, inplace=True)
    df['_probability'] = df['_probability'].astype(float)
    
    df['_end_mission'] = df['_end_mission'].apply(get_first_list)
    df['_end_mission'] = pd.to_datetime(df['_end_mission'])
            
    df = summarise_start_end(df) 
    
    df['_prob_require'] = df['_capacity'] * df['_probability']
       
    return df

@st.experimental_memo()
def get_mission_logs(df_logs: pd.DataFrame) -> pd.DataFrame:
    
    df  = df_logs[df_logs['State'] != "Rejected"]
    
    df = air_join(df_logs, roles, "Role")
    df = air_join(df, missions, "Mission")
    df = air_join(df, clients, "Client")
    df = air_join(df, explorers, "EXPLORER")
    
    df['_requirement'] = df['mission_requirement'].apply(get_first_list)
    df = df[df["Scenario"] != "Rejected"]
    
    df['_probability'] = df['_prob'].apply(get_first_list)
    df['_probability'].fillna(0.0, inplace=True)
    df['_probability'] = df['_probability'].astype(float)
    
    df = summarise_start_end(df) 
    
    df_require = df.groupby(['_requirement', 'Month_End']).sum('_capacity')
    
    return df, df_require

@st.experimental_memo()
def get_require_gaps(df_requirements: pd.DataFrame, df_require_logs: pd.DataFrame) -> pd.DataFrame:
    
    df_gaps = df_requirements.reset_index().join(df_require_logs, on=['id', 'Month_End'], rsuffix='_logs')
    
    df_gaps['_capacity_logs'].fillna(0.0, inplace=True)
    df_gaps['Gap'] = df_gaps['_capacity'] - df_gaps['_capacity_logs']
    
    df_gaps.reset_index(inplace=True)
    
    return df_gaps

@st.experimental_memo()
def get_explorer_allocations(df_mission_logs, explorers: pd.DataFrame):
    
    df = df_mission_logs[df_mission_logs['_capacity'] != 0]
    
    df_explorers = df.groupby(["EXPLORER", 'Month_End']).sum('_capacity')
    df_explorers.reset_index(inplace=True)
    df_explorers.set_index("EXPLORER", inplace=True)
    df_explorers = explorers.join(df_explorers)
    df_explorers['_capacity'].fillna(0, inplace=True)
    df_explorers['Availability'] = df_explorers['_capacity'] - 1 if df_explorers['Active'] else 0
    
    return df_explorers

# enrich nodes
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
            
    return df_temp

@st.experimental_memo()
def project_requirements(df: pd.DataFrame) -> pd.DataFrame:
    df['_projected'] = df['_capacity'] * df['_probability']
    df.loc[df["Month_End"] > df['_end_mission'], '_projected'] = df["Capacity"] * df['_renewal']
    return df

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

@st.experimental_memo()
def enrich_data(requirements, logs, explorers):
    df_requirements = get_mission_requirements(requirements)
    df_requirements = project_requirements(df_requirements)
    
    df_mission_logs, df_require_logs = get_mission_logs(logs)
    df_gaps = get_require_gaps(df_requirements, df_require_logs)
    
    df_explorers = get_explorer_allocations(df_mission_logs, explorers)
    
    # TODO: find out why i need to do 
    df_requirements.reset_index(inplace=True)
    df_requirements.set_index(['id'], inplace=True)
    
    return df_requirements, df_mission_logs, df_require_logs, df_gaps, df_explorers

# serve nodes
def color_allocted(value: float) -> str:
    if value > 1:
        color = 'red' 
    elif value < 1:
        color = 'green'
    else:
        return None
    return f'background-color: {color}'
    
def get_base_chart(data, groupby: str, values: str = "_capacity"):
    
    base = alt.Chart(data).encode(x="Month_End")
    bar = base.mark_bar(size=20).encode(y=f"sum({values})", color=f"{groupby}:O")
    
    return base, bar

def get_projected_chart(base: alt.Chart):
    
    line = base.mark_line(color='red', strokeWidth=5).encode(y="sum(_prob_require)")
    line_projected = base.mark_line(color='red', strokeDash=[5, 2], strokeWidth=5).encode(y="sum(_projected)")
    
    return line, line_projected

# start here
st.set_page_config(
    page_title="ExploreAI Mission Requirements", page_icon="⬇", layout="centered"
)

st.image(image='eai.png',caption='https://explore.ai')

# ingest data
roles, missions, clients, explorers, scenarios, requirements, logs = get_raw_data()

# enrich data
df_requirements, df_mission_logs, df_require_logs, df_gaps, df_explorers = enrich_data(requirements, logs, explorers)

# define the streamlit sidebar
choice_start    = st.sidebar.date_input('Select your start date:', value=pd.to_datetime('2022-04-01')) 
choice_end      = st.sidebar.date_input('Select your end date:', value=pd.to_datetime('2023-06-30')) 
choice_groupby  = st.sidebar.radio('Select what to group by:', ('None', 'Seniority', "Role_Name", "Mission_Name", 'Client_Name', "Scenario")) 
choice_role     = st.sidebar.multiselect('Select your Roles:', roles['Role'].unique())
choice_client   = st.sidebar.multiselect('Select your Client:', clients['Client'].unique())
choice_mission  = st.sidebar.multiselect('Select your Mission:', missions['Mission'].unique())
choice_scenario = st.sidebar.multiselect('Select your Scenarios:', scenarios['Scenario'].unique(), disabled=True)

requirements_filter = {
    "Role_Name" : choice_role,
    "Client_Name" : choice_client,
    "Mission_Name" : choice_mission,
    "Scenario_Name" : choice_scenario,
    }

tab_require, tab_allocate, tab_gap, tab_explorers, tab_missions, tab_data = st.tabs(["Requirements", "Allocations", "Gaps", "Explorers", "Missions", "All Data"])

with tab_missions:
    st.title("Mission Details")
    st.dataframe(missions)

with tab_data:

    st.write("Requirements table")
    st.dataframe(df_requirements)
    st.download_button(
        "Download Requirements",
        convert_df(df_requirements),
        "requirements.csv",
        "text/csv",
        key='download-requirements'
    )
    
    st.write("Mission Logs")

    st.dataframe(df_mission_logs)
    st.download_button(
        "Download Requirements",
        convert_df(df_mission_logs),
        "mission_logs.csv",
        "text/csv",
        key='download-mission_logs'
    )
    st.write("Requirement Mission Logs")
    st.dataframe(df_require_logs.head())
    
    st.write("Explorers")
    st.dataframe(df_explorers)

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
        
    df = df_filter_dates(df_explorers, start_date=choice_start, end_date=choice_end)
    df = df_filter_isin(df, requirements_filter)
    
    base, bar = get_base_chart(df, groupby="Role_Name", values="Availability")
    st.altair_chart(bar, use_container_width=True)
    
    show_not_allocated = st.checkbox("Show only Explorers not fully allocated")

    df_table = df.reset_index()
    df_table = df_table.pivot_table(index='index', columns="Month_End", values="_capacity", fill_value=0, aggfunc="sum")

    df_table.rename(columns={col: str(col)[0:10] for col in df_table.columns}, inplace=True)
    df_table['_average_allocation'] = abs(df_table.mean(axis=1) - 1)    
    
    explorer_cols = ['EXPLORER', "Role_Name", 'Belt Colour', 'Active']
    df_table = df_table.join(explorers[explorer_cols])
    
    df_table['Active'].fillna(False, inplace=True)
    df_table = df_table[df_table['Active']]

    df_table.set_index(explorer_cols, inplace=True)
    
    df_table.sort_values('_average_allocation', ascending=False, inplace=True) 
    
    if show_not_allocated:
        df_table = df_table[df_table['_average_allocation'] != 0]

    st.dataframe(df_table.style.applymap(color_allocted).format("{:.1%}"))
    
    st.download_button(
        "Download Explorer Allocations",
        convert_df(df),
        "allocations.csv",
        "text/csv",
        key='download-explorer-allocations'
    )


    

