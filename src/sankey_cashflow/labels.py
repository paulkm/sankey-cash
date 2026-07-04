from typing import Optional, Union

import networkx as nx
from numpy.typing import ArrayLike

from .utils import is_null, logger


class RowLabels:
    """
      Contains row label data and methods, used to map data categories to source, target, and color information.
      Accepts an array of dicts on init which can come from a Google sheet or csv.
      Data looks like: [{'Category Name': 'House', 'Type': 'computed', 'Source': 'Income', 'Target': 'House',
        'Link color': 'rgba(153, 187, 255, 0.8)', 'Node color': 'rgba(102, 153, 255, 1)', 'Comments': '', '': ''}]
      Also creates a DAG with source target edges based on labels definitions
    """
    def __init__(self, labeldata: list[dict]):
        self._labeldata = labeldata
        self._digraph = nx.DiGraph()
        self._digraph.add_node("Income", ntype="income")
        self.process_report = f"RowLabel report\n{'=' * 60}\n\n\n"
        required_columns = ['Category Name', 'Type', 'Source', 'Target', 'Classification', 'Link color', 'Node color']
        if False in [k in self._labeldata[0].keys() for k in required_columns]:
            raise Exception(f"Sources-Targets sheet does not have all required columns! Needed: {required_columns}. \
                            Found: {list(self._labeldata[0].keys())}")
        self._available_attributes = ['source', 'target', 'classification', 'link_color', 'node_color', 'type']
        # TODO: validation
        self._lookup = {}
        # Map out data to lookup dict
        for i in self._labeldata:
            if len(i['Category Name']) == 0:  # Skip empties
                self.process_report += f"SKIPPING: {i}\n"
                continue
            if i['Category Name'] in self._lookup:
                raise Exception(f"Duplicate label! {i['Category Name']}")
            # Add to internal lookup dict
            self.process_report += f"ADDING LOOKUP: {i}\n"
            self._lookup[i['Category Name']] = {
                'source': i.get('Source'),
                'target': i.get('Target'),
                'classification': i.get('Classification'),
                'link_color': i.get('Link color'),
                'node_color': i.get('Node color'),
                'type': i.get('Type')
            }
            if i.get("Source") == "DEDUCTIONS":
                # These have to be dynamically generated - skip adding to DAG for now (or maybe entirely)
                # TODO (maybe): switch to using type and/or DAG attributes
                self.process_report += f"SKIPPING DEDUCTION: {i}\n"
                continue
            if i["Type"] in ['tag', 's-tag']:
                # NOT adding tag labels to graph - if needed they will be added on the fly
                # TODO: investigate using DAG attributes instead. Test with distant/complex tag targets.
                if i["Type"] == 's-tag':
                    self.process_report += f"Adding NODE for s-tag: {i} to DAG\n"
                    self._digraph.add_node(i['Category Name'], type='s-tag')
                else:
                    self.process_report += f"NOT Adding tag: {i} to DAG\n"
                continue
            if i.get('Source') and i.get('Target'):  # Add all source/target pairs as edges to DAG
                # Add to DAG
                if i.get('Type'):
                    self.process_report += \
                        f"ADDING EDGE: {i.get('Source')} -> {i.get('Target')} (ntype={i.get('Type')})\n"
                    self._digraph.add_edge(i.get('Source'), i.get('Target'), ntype=i.get('Type'))
                else:
                    self.process_report += f"ADDING EDGE: {i.get('Source')} -> {i.get('Target')}\n"
                    self._digraph.add_edge(i.get('Source'), i.get('Target'))
            else:
                self.process_report += f"ERROR (SKIPPING): {i}\n"
                logger.warning(f"Category: {i['Category Name']} yielded an empty source and/or target! \
                            {i.get('Source')}:{i.get('Target')}")

    @property
    def data(self) -> list[dict]:
        return self._labeldata

    @property
    def graph(self) -> nx.DiGraph:
        return self._digraph

    def get_longest_path(self) -> ArrayLike:
        return nx.dag_longest_path(self._digraph)

    def get_path(self, source: str, target: str) -> Union[list, None]:
        path = [i for i in nx.all_simple_paths(self._digraph, source, target)]
        # Note path obj may contain 0 or multiple paths
        if not path or len(path) == 0:
            logger.warning(f"No path found for {source}:{target}")
        elif len(path) > 1:
            logger.warning(f"Multiple paths found for {source}:{target}. ({path})")
        else:
            return path[0]

    def get_label(self, labelname: str, labeltype: Union[str, None] = None) -> Union[tuple[str, str], None]:
        """
          Return a label name & tag pair or None
        """
        item = self._lookup.get(labelname)  # TODO: test duplicate category names
        if labeltype == "any":
            return item
        if labeltype and labeltype == "tag":
            if item and item.get('type') == 'tag':
                return item
            return None
        elif labeltype and labeltype == "s-tag":
            if item and item.get('type') == 's-tag':
                return item
            return None
        if item and item.get('type') not in ['tag', 's-tag']:
            return item
        return None

    def get_attribute(self,
                      labelname: str,
                      labelattribute: str,
                      use_default: Optional[bool] = True,
                      labeltype: Optional[Union[str, None]] = None,
                      original_category: Optional[Union[str, None]] = None) -> Union[str, None]:
        """
          Get named attribute by label. Cases:
            Unknown attribute: raise exception
            label & labeltype are exist:
              attribute exists: return attribute
              attribute doesn't exist: return default attribute
            label & labeltype doesn't exists:
              return default attributes
        """
        if labelattribute not in self._available_attributes:
            raise Exception(f"Unknown attribute: {labelattribute}")
        if labelattribute == "type":
            item = self.get_label(labelname, "any")
        else:
            item = self.get_label(labelname, labeltype)
        default_item = self.get_label('default')
        if item:
            if labelattribute == "type":
                return item.get("type", "")
            if not is_null(item[labelattribute]) and len(item[labelattribute]) != 0:
                return item[labelattribute]
        elif labelattribute == "type":
            return None
        if use_default:
            # Did not find the attribute - use defaults
            if labelattribute == "source":
                return "Uncategorized"
            if labelattribute == "target":
                return labelname
            if labelattribute == "classification":
                return 'Uncategorized'
            if labelattribute in ["node_color", "link_color"]:
                return default_item[labelattribute]
        return None

    def print_graph(self, filename: str) -> None:
        from matplotlib import pyplot as plt
        plt.tight_layout()
        nx.draw_networkx(self._digraph, arrows=True)
        # plt.figure(figsize=(20,20))
        plt.savefig(filename, dpi=200, format="PNG")
        plt.clf()
