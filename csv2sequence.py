import argparse
import ast
import json
import os
import sys
import config
from typing import List
from funutils import Maybe, first, just

import pandas as pd


# TODO: Document all functions

def main():
    args = parse_command_line()
    setup()
    files = generate_fdl_files(args)
    generate_project(files, args)

    # TODO: Add support for document generation


def parse_command_line():
    parser = argparse.ArgumentParser(description='Convert a CSV file into Sequence Diagram')
    parser.add_argument('csv_file', metavar='csv_file', nargs='+',
                        help='CSV file to be converted to a sequence diagram')
    parser.add_argument('-m', '--merge', action='store_true',
                        help='merge the CSV files with entities arranged in time order')
    parser.add_argument('-s', '--sort', action='store_true',
                        help='sort the headers in the generated sequence diagram')
    parser.add_argument('-o', '--output',
                        help='specify the output directory for the sequence diagram project')
    # TODO: Add an argument for controlling the output
    args = parser.parse_args()
    if not args.output:
        args.output = os.path.dirname(args.csv_file[0])
    print(args)
    return args


def setup():
    pd.options.mode.use_inf_as_na = True  # Treat null and inf also as missing data in a isna call


def generate_fdl_files(args) -> List[str]:
    files = []
    if args.merge:
        # Read all the CSV files and combine them into a single data frame
        # https://pandas.pydata.org/pandas-docs/stable/user_guide/merging.html
        frames = []
        for file in args.csv_file:
            df = read_data_frame(file)
            frames.append(df)
        merged_file_path = os.path.join(args.output, 'merged')
        combined_frame = pd.concat(frames).drop_duplicates().reset_index(drop=True)
        combined_frame = update_data_frame_types(combined_frame)
        combined_frame.sort_values(['Timestamp'], inplace=True)
        generate_sequence_diagram(combined_frame, merged_file_path, args)
        files = ['merged']
    else:
        for file in args.csv_file:
            file_title = os.path.basename[0]  # Remove file extension
            df = read_data_frame(file)
            df = update_data_frame_types(df)
            generate_sequence_diagram(df, file_title, args)
            files.append(file)
    return files


def generate_sequence_diagram(scenario_df: pd.DataFrame, scenario_name: str, args):
    column_values = scenario_df[['Source', 'Destination']].values.ravel()
    entities = pd.unique(column_values)
    os.makedirs(os.path.dirname(scenario_name), exist_ok=True)
    with open(scenario_name + '.FDL', 'w') as fdl:
        if config.theme_template is not None:
            fdl.write(f'#include <{config.theme_template}.FDL>\n')
        fdl.write('#include <stdinc.FDL>\n\n')
        fdl.write('#include "VisualEtherStyles.FDL"\n')

        if args.sort:
            entities.sort()

        for entity in entities:
            fdl.write(f'eternal: "{entity}"\n')

        fdl.write(f'feature "{scenario_name}" {{\n')

        for statement in scenario_df.itertuples():
            indentation = config.indent
            if hasattr(statement, 'Bookmark') and statement.Bookmark:
                fdl.write(f'{indentation}heading "{statement.Message}"\n')

            if hasattr(statement, 'Style') and statement.Style:
                fdl.write(f'{indentation}[{statement.Style}] ')
                indentation = ''

            parameters = ''
            if hasattr(statement, 'Parameters') and type(statement.Parameters) == list:
                parameters = format_parameters(statement.Parameters)

            source_port = ''
            if hasattr(statement, 'SourcePort') and (not pd.isna(statement.SourcePort)):
                source_port = f'-"{statement.DestinationPort}"'

            destination_port = ''
            if hasattr(statement, 'DestinationPort') and (not pd.isna(statement.DestinationPort)):
                destination_port = f'-"{statement.DestinationPort}"'

            fdl.write(
                f'{indentation}"{statement.Message}" {parameters}: "{statement.Source}"{source_port} -> "{statement.Destination}"{destination_port}')

            if hasattr(statement, 'Hyperlink') and statement.Hyperlink:
                fdl.write(f' <{statement.Hyperlink}>')
            fdl.write('\n')

            if statement.Timestamp:
                if hasattr(statement, 'Frame') and statement.Frame:
                    fdl.write(f'    |* {statement.Frame}: {statement.Timestamp} *|\n\n')
                else:
                    fdl.write(f'    |* {statement.Timestamp} *|\n\n')
        fdl.write('}\n')


def format_parameters(parameters: list) -> str:
    indentation = config.indent*2
    formatted_params = ''
    separator = ''

    formatted_params = '('
    for param in parameters:
        if type(param) == tuple:
            formatted_params += f'{separator}"{param[0]}" = "{param[1]}"'
        else:
            formatted_params += f'{separator}"{param}"'
        separator = f',\n{indentation}'
    formatted_params += ')'

    return formatted_params


def validate_csv_file(file: str, df: pd.DataFrame):
    mandatory_columns = {'Timestamp', 'Source', 'Destination', 'Message'}

    if not mandatory_columns.issubset(df.columns):
        sys.exit(f'{file} should contain mandatory fields:\n{mandatory_columns}\n')


def try_literal_eval(val):
    try:
        return ast.literal_eval(val)
    except ValueError:
        return val


def read_data_frame(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    validate_csv_file(file, df)
    return df


def update_data_frame_types(df) -> pd.DataFrame:
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='s')
    df['Parameters'] = df['Parameters'].apply(try_literal_eval)
    return df


def generate_project(fdl_files: List[str], args):
    scenario_project = {
        "documents": [
            {
                "columnWidth": "medium",
                "documentFormat": "pdf",
                "documentName": "SequenceDiagram",
                "documentType": "sequence-diagram",
                "remarkWidth": "small"
            },
            {
                "documentFormat": "pdf",
                "documentName": "ContextDiagram",
                "documentType": "context-diagram",
                "internalMargin": "small",
                "objectSpacing": "small"
            }],
        "scenarios": []
    }

    for fdl in fdl_files:
        file_title = os.path.splitext(fdl)[0]
        scenario_project["scenarios"].append({
            "modelPath": file_title + '.FDL',
            "scenarioName": file_title
        })

    # Serializing json
    json_object = json.dumps(scenario_project, indent=4)

    # Writing the project file
    project_file_path = os.path.join(args.output, 'project.scn.json')
    os.makedirs(args.output, exist_ok=True)
    with open(project_file_path, "w") as project_file:
        project_file.write(json_object)


if __name__ == '__main__':
    main()
