import networkx as nx
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import database.crud as crud

logger = logging.getLogger(__name__)

class GraphHandler:
    def __init__(self):
        self.graph = nx.DiGraph()

    async def load_graph_from_db(self, db_session: AsyncSession):
        """Loads tags and relationships from the database into a networkx DiGraph."""
        logger.info("Loading knowledge graph from database...")
        try:
            tags = await crud.get_all_tags(db_session)
            relationships = await crud.get_all_tag_relationships(db_session)

            self.graph.clear()
            
            # Add nodes
            for tag in tags:
                self.graph.add_node(
                    tag.id,
                    name=tag.name,
                    category=tag.category,
                    subcategory=tag.subcategory,
                    cefr_level=tag.cefr_level,
                    logic_group=tag.logic_group,
                    visibility=tag.visibility
                )
            
            # Add edges
            for rel in relationships:
                # Direction: source_tag -> target_tag
                # e.g., PREREQUISITE: Source is prerequisite for Target
                self.graph.add_edge(
                    rel.source_tag_id,
                    rel.target_tag_id,
                    type=rel.relationship_type,
                    weight=rel.weight
                )
            
            logger.info(f"Knowledge graph loaded: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges.")
        except Exception as e:
            logger.error(f"Failed to load knowledge graph: {e}", exc_info=True)
            raise

    def get_tag_details(self, tag_id: int) -> Optional[Dict[str, Any]]:
        """Returns the attributes of a specific tag node."""
        if tag_id in self.graph:
            return self.graph.nodes[tag_id]
        return None

    def get_prerequisites(self, tag_id: int) -> List[int]:
        """Returns direct prerequisite tag IDs for a given tag."""
        if tag_id not in self.graph:
            return []
        return [
            u for u, v, d in self.graph.in_edges(tag_id, data=True)
            if d.get("type") == "PREREQUISITE"
        ]

    def get_dependents(self, tag_id: int) -> List[int]:
        """Returns tags that have this tag as a prerequisite."""
        if tag_id not in self.graph:
            return []
        return [
            v for u, v, d in self.graph.out_edges(tag_id, data=True)
            if d.get("type") == "PREREQUISITE"
        ]

    def get_all_prerequisites_recursive(self, tag_id: int) -> List[int]:
        """Returns all transitive prerequisites for a tag (upstream in the graph)."""
        if tag_id not in self.graph:
            return []
        
        # Subgraph containing only PREREQUISITE edges
        prereq_edges = [
            (u, v) for u, v, d in self.graph.edges(data=True) 
            if d.get("type") == "PREREQUISITE"
        ]
        prereq_graph = nx.DiGraph(prereq_edges)
        
        if tag_id not in prereq_graph:
            return []
            
        return list(nx.ancestors(prereq_graph, tag_id))

    def find_path(self, start_tag_id: int, end_tag_id: int) -> Optional[List[int]]:
        """Finds a path between two tags if it exists."""
        try:
            return nx.shortest_path(self.graph, source=start_tag_id, target=end_tag_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def get_graph_stats(self) -> Dict[str, int]:
        """Returns basic information about the graph."""
        return {
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges()
        }
