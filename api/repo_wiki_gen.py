"""
Repository Wiki Generation Module
Ported from src/app/[owner]/[repo]/page.tsx
"""

import os
import json
import logging
from typing import Dict, List, Optional, Set, Literal
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET
import re
import base64

logger = logging.getLogger(__name__)


@dataclass
class WikiSection:
    """Represents a section in the wiki structure"""
    id: str
    title: str
    pages: List[str]
    subsections: Optional[List[str]] = None


@dataclass
class WikiPage:
    """Represents a wiki page"""
    id: str
    title: str
    content: str
    file_paths: List[str]
    importance: Literal['high', 'medium', 'low']
    related_pages: List[str]
    parent_id: Optional[str] = None
    is_section: bool = False
    children: Optional[List[str]] = None


@dataclass
class WikiStructure:
    """Represents the complete wiki structure"""
    id: str
    title: str
    description: str
    pages: List[WikiPage]
    sections: List[WikiSection] = field(default_factory=list)
    root_sections: List[str] = field(default_factory=list)


@dataclass
class RepoInfo:
    """Repository information"""
    owner: str
    repo: str
    type: str  # 'github', 'gitlab', 'bitbucket', 'local'
    token: Optional[str] = None
    local_path: Optional[str] = None
    repo_url: Optional[str] = None


class WikiGenerator:
    """Wiki generation orchestrator"""
    
    def __init__(
        self,
        repo_info: RepoInfo,
        language: str = 'en',
        provider: str = '',
        model: str = '',
        is_custom_model: bool = False,
        custom_model: str = '',
        excluded_dirs: str = '',
        excluded_files: str = '',
        included_dirs: str = '',
        included_files: str = '',
        is_comprehensive: bool = True
    ):
        self.repo_info = repo_info
        self.language = language
        self.provider = provider
        self.model = model
        self.is_custom_model = is_custom_model
        self.custom_model = custom_model
        self.excluded_dirs = excluded_dirs
        self.excluded_files = excluded_files
        self.included_dirs = included_dirs
        self.included_files = included_files
        self.is_comprehensive = is_comprehensive
        self.default_branch = 'main'
        
        # State tracking
        self.generated_pages: Dict[str, WikiPage] = {}
        self.pages_in_progress: Set[str] = set()
        self.active_content_requests: Set[str] = set()
        
    def get_cache_key(self) -> str:
        """Generate cache key for localStorage"""
        return f"deepwiki_cache_{self.repo_info.type}_{self.repo_info.owner}_{self.repo_info.repo}_{self.language}_{'comprehensive' if self.is_comprehensive else 'concise'}"
    
    def add_tokens_to_request_body(self, request_body: Dict) -> None:
        """Add authentication tokens and parameters to request body"""
        if self.repo_info.token:
            request_body['token'] = self.repo_info.token
        
        request_body['provider'] = self.provider
        request_body['model'] = self.model
        if self.is_custom_model and self.custom_model:
            request_body['custom_model'] = self.custom_model
        
        request_body['language'] = self.language
        
        # Add file filter parameters
        if self.excluded_dirs:
            request_body['excluded_dirs'] = self.excluded_dirs
        if self.excluded_files:
            request_body['excluded_files'] = self.excluded_files
        if self.included_dirs:
            request_body['included_dirs'] = self.included_dirs
        if self.included_files:
            request_body['included_files'] = self.included_files
    
    def create_github_headers(self, github_token: str) -> Dict[str, str]:
        """Create headers for GitHub API requests"""
        headers = {'Accept': 'application/vnd.github.v3+json'}
        if github_token:
            headers['Authorization'] = f'Bearer {github_token}'
        return headers
    
    def create_gitlab_headers(self, gitlab_token: str) -> Dict[str, str]:
        """Create headers for GitLab API requests"""
        headers = {'Content-Type': 'application/json'}
        if gitlab_token:
            headers['PRIVATE-TOKEN'] = gitlab_token
        return headers
    
    def create_bitbucket_headers(self, bitbucket_token: str) -> Dict[str, str]:
        """Create headers for Bitbucket API requests"""
        headers = {'Content-Type': 'application/json'}
        if bitbucket_token:
            headers['Authorization'] = f'Bearer {bitbucket_token}'
        return headers
    
    def generate_file_url(self, file_path: str) -> str:
        """Generate proper repository file URLs"""
        if self.repo_info.type == 'local':
            return file_path
        
        repo_url = self.repo_info.repo_url
        if not repo_url:
            return file_path
        
        try:
            from urllib.parse import urlparse
            url = urlparse(repo_url)
            hostname = url.hostname
            
            if hostname and ('github' in hostname):
                # GitHub URL format: https://github.com/owner/repo/blob/branch/path
                return f"{repo_url}/blob/{self.default_branch}/{file_path}"
            elif hostname and ('gitlab' in hostname):
                # GitLab URL format: https://gitlab.com/owner/repo/-/blob/branch/path
                return f"{repo_url}/-/blob/{self.default_branch}/{file_path}"
            elif hostname and ('bitbucket' in hostname):
                # Bitbucket URL format: https://bitbucket.org/owner/repo/src/branch/path
                return f"{repo_url}/src/{self.default_branch}/{file_path}"
        except Exception as e:
            logger.warning(f'Error generating file URL: {e}')
        
        return file_path
    
    def get_language_name(self) -> str:
        """Get full language name from language code"""
        language_map = {
            'en': 'English',
            'ja': 'Japanese (日本語)',
            'zh': 'Mandarin Chinese (中文)',
            'zh-tw': 'Traditional Chinese (繁體中文)',
            'es': 'Spanish (Español)',
            'kr': 'Korean (한국어)',
            'vi': 'Vietnamese (Tiếng Việt)',
            'pt-br': 'Brazilian Portuguese (Português Brasileiro)',
            'fr': 'Français (French)',
            'ru': 'Русский (Russian)'
        }
        return language_map.get(self.language, 'English')
    
    def create_page_content_prompt(self, page: WikiPage) -> str:
        """Create prompt for generating page content"""
        file_links = '\n'.join([
            f"- [{path}]({self.generate_file_url(path)})"
            for path in page.file_paths
        ])
        
        prompt = f'''You are an expert technical writer and software architect.
Your task is to generate a comprehensive and accurate technical wiki page in Markdown format about a specific feature, system, or module within a given software project.

You will be given:
1. The "[WIKI_PAGE_TOPIC]" for the page you need to create.
2. A list of "[RELEVANT_SOURCE_FILES]" from the project that you MUST use as the sole basis for the content. You have access to the full content of these files. You MUST use AT LEAST 5 relevant source files for comprehensive coverage - if fewer are provided, search for additional related files in the codebase.

CRITICAL STARTING INSTRUCTION:
The very first thing on the page MUST be a `<details>` block listing ALL the `[RELEVANT_SOURCE_FILES]` you used to generate the content. There MUST be AT LEAST 5 source files listed - if fewer were provided, you MUST find additional related files to include.
Format it exactly like this:
<details>
<summary>Relevant source files</summary>

Remember, do not provide any acknowledgements, disclaimers, apologies, or any other preface before the `<details>` block. JUST START with the `<details>` block.
The following files were used as context for generating this wiki page:

{file_links}
<!-- Add additional relevant files if fewer than 5 were provided -->
</details>

Immediately after the `<details>` block, the main title of the page should be a H1 Markdown heading: `# {page.title}`.

Based ONLY on the content of the `[RELEVANT_SOURCE_FILES]`:

1.  **Introduction:** Start with a concise introduction (1-2 paragraphs) explaining the purpose, scope, and high-level overview of "{page.title}" within the context of the overall project. If relevant, and if information is available in the provided files, link to other potential wiki pages using the format `[Link Text](#page-anchor-or-id)`.

2.  **Detailed Sections:** Break down "{page.title}" into logical sections using H2 (`##`) and H3 (`###`) Markdown headings. For each section:
    *   Explain the architecture, components, data flow, or logic relevant to the section's focus, as evidenced in the source files.
    *   Identify key functions, classes, data structures, API endpoints, or configuration elements pertinent to that section.

3.  **Mermaid Diagrams:**
    *   EXTENSIVELY use Mermaid diagrams (e.g., `flowchart TD`, `sequenceDiagram`, `classDiagram`, `erDiagram`, `graph TD`) to visually represent architectures, flows, relationships, and schemas found in the source files.
    *   Ensure diagrams are accurate and directly derived from information in the `[RELEVANT_SOURCE_FILES]`.
    *   Provide a brief explanation before or after each diagram to give context.
    *   CRITICAL: All diagrams MUST follow strict vertical orientation:
       - Use "graph TD" (top-down) directive for flow diagrams
       - NEVER use "graph LR" (left-right)
       - Maximum node width should be 3-4 words
       - For sequence diagrams:
         - Start with "sequenceDiagram" directive on its own line
         - Define ALL participants at the beginning using "participant" keyword
         - Optionally specify participant types: actor, boundary, control, entity, database, collections, queue
         - Use descriptive but concise participant names, or use aliases: "participant A as Alice"
         - Use the correct Mermaid arrow syntax (8 types available):
           - -> solid line without arrow (rarely used)
           - --> dotted line without arrow (rarely used)
           - ->> solid line with arrowhead (most common for requests/calls)
           - -->> dotted line with arrowhead (most common for responses/returns)
           - ->x solid line with X at end (failed/error message)
           - -->x dotted line with X at end (failed/error response)
           - -) solid line with open arrow (async message, fire-and-forget)
           - --) dotted line with open arrow (async response)
           - Examples: A->>B: Request, B-->>A: Response, A->xB: Error, A-)B: Async event
         - Use +/- suffix for activation boxes: A->>+B: Start (activates B), B-->>-A: End (deactivates B)
         - Group related participants using "box": box GroupName ... end
         - Use structural elements for complex flows:
           - loop LoopText ... end (for iterations)
           - alt ConditionText ... else ... end (for conditionals)
           - opt OptionalText ... end (for optional flows)
           - par ParallelText ... and ... end (for parallel actions)
           - critical CriticalText ... option ... end (for critical regions)
           - break BreakText ... end (for breaking flows/exceptions)
         - Add notes for clarification: "Note over A,B: Description", "Note right of A: Detail"
         - Use autonumber directive to add sequence numbers to messages
         - NEVER use flowchart-style labels like A--|label|-->B. Always use a colon for labels: A->>B: My Label

4.  **Tables:**
    *   Use Markdown tables to summarize information such as:
        *   Key features or components and their descriptions.
        *   API endpoint parameters, types, and descriptions.
        *   Configuration options, their types, and default values.
        *   Data model fields, types, constraints, and descriptions.

5.  **Code Snippets (ENTIRELY OPTIONAL):**
    *   Include short, relevant code snippets (e.g., Python, Java, JavaScript, SQL, JSON, YAML) directly from the `[RELEVANT_SOURCE_FILES]` to illustrate key implementation details, data structures, or configurations.
    *   Ensure snippets are well-formatted within Markdown code blocks with appropriate language identifiers.

6.  **Source Citations (EXTREMELY IMPORTANT):**
    *   For EVERY piece of significant information, explanation, diagram, table entry, or code snippet, you MUST cite the specific source file(s) and relevant line numbers from which the information was derived.
    *   Place citations at the end of the paragraph, under the diagram/table, or after the code snippet.
    *   Use the exact format: `Sources: [filename.ext:start_line-end_line]()` for a range, or `Sources: [filename.ext:line_number]()` for a single line. Multiple files can be cited: `Sources: [file1.ext:1-10](), [file2.ext:5](), [dir/file3.ext]()` (if the whole file is relevant and line numbers are not applicable or too broad).
    *   If an entire section is overwhelmingly based on one or two files, you can cite them under the section heading in addition to more specific citations within the section.
    *   IMPORTANT: You MUST cite AT LEAST 5 different source files throughout the wiki page to ensure comprehensive coverage.

7.  **Technical Accuracy:** All information must be derived SOLELY from the `[RELEVANT_SOURCE_FILES]`. Do not infer, invent, or use external knowledge about similar systems or common practices unless it's directly supported by the provided code. If information is not present in the provided files, do not include it or explicitly state its absence if crucial to the topic.

8.  **Clarity and Conciseness:** Use clear, professional, and concise technical language suitable for other developers working on or learning about the project. Avoid unnecessary jargon, but use correct technical terms where appropriate.

9.  **Conclusion/Summary:** End with a brief summary paragraph if appropriate for "{page.title}", reiterating the key aspects covered and their significance within the project.

IMPORTANT: Generate the content in {self.get_language_name()} language.

Remember:
- Ground every claim in the provided source files.
- Prioritize accuracy and direct representation of the code's functionality and structure.
- Structure the document logically for easy understanding by other developers.
'''
        return prompt
    
    def create_wiki_structure_prompt(self, file_tree: str, readme: str) -> str:
        """Create prompt for determining wiki structure"""
        pages_count = '8-12' if self.is_comprehensive else '4-6'
        
        structure_section = ""
        if self.is_comprehensive:
            structure_section = '''
Create a structured wiki with the following main sections:
- Overview (general information about the project)
- System Architecture (how the system is designed)
- Core Features (key functionality)
- Data Management/Flow: If applicable, how data is stored, processed, accessed, and managed (e.g., database schema, data pipelines, state management).
- Frontend Components (UI elements, if applicable.)
- Backend Systems (server-side components)
- Model Integration (AI model connections)
- Deployment/Infrastructure (how to deploy, what's the infrastructure like)
- Extensibility and Customization: If the project architecture supports it, explain how to extend or customize its functionality (e.g., plugins, theming, custom modules, hooks).

Each section should contain relevant pages. For example, the "Frontend Components" section might include pages for "Home Page", "Repository Wiki Page", "Ask Component", etc.

Return your analysis in the following XML format:

<wiki_structure>
  <title>[Overall title for the wiki]</title>
  <description>[Brief description of the repository]</description>
  <sections>
    <section id="section-1">
      <title>[Section title]</title>
      <pages>
        <page_ref>page-1</page_ref>
        <page_ref>page-2</page_ref>
      </pages>
      <subsections>
        <section_ref>section-2</section_ref>
      </subsections>
    </section>
    <!-- More sections as needed -->
  </sections>
  <pages>
    <page id="page-1">
      <title>[Page title]</title>
      <description>[Brief description of what this page will cover]</description>
      <importance>high|medium|low</importance>
      <relevant_files>
        <file_path>[Path to a relevant file]</file_path>
        <!-- More file paths as needed -->
      </relevant_files>
      <related_pages>
        <related>page-2</related>
        <!-- More related page IDs as needed -->
      </related_pages>
      <parent_section>section-1</parent_section>
    </page>
    <!-- More pages as needed -->
  </pages>
</wiki_structure>
'''
        else:
            structure_section = '''
Return your analysis in the following XML format:

<wiki_structure>
  <title>[Overall title for the wiki]</title>
  <description>[Brief description of the repository]</description>
  <pages>
    <page id="page-1">
      <title>[Page title]</title>
      <description>[Brief description of what this page will cover]</description>
      <importance>high|medium|low</importance>
      <relevant_files>
        <file_path>[Path to a relevant file]</file_path>
        <!-- More file paths as needed -->
      </relevant_files>
      <related_pages>
        <related>page-2</related>
        <!-- More related page IDs as needed -->
      </related_pages>
    </page>
    <!-- More pages as needed -->
  </pages>
</wiki_structure>
'''
        
        prompt = f'''Analyze this GitHub repository {self.repo_info.owner}/{self.repo_info.repo} and create a wiki structure for it.

1. The complete file tree of the project:
<file_tree>
{file_tree}
</file_tree>

2. The README file of the project:
<readme>
{readme}
</readme>

I want to create a wiki for this repository. Determine the most logical structure for a wiki based on the repository's content.

IMPORTANT: The wiki content will be generated in {self.get_language_name()} language.

When designing the wiki structure, include pages that would benefit from visual diagrams, such as:
- Architecture overviews
- Data flow descriptions
- Component relationships
- Process workflows
- State machines
- Class hierarchies

{structure_section}

IMPORTANT FORMATTING INSTRUCTIONS:
- Return ONLY the valid XML structure specified above
- DO NOT wrap the XML in markdown code blocks (no ``` or ```xml)
- DO NOT include any explanation text before or after the XML
- Ensure the XML is properly formatted and valid
- Start directly with <wiki_structure> and end with </wiki_structure>

IMPORTANT:
1. Create {pages_count} pages that would make a {'comprehensive' if self.is_comprehensive else 'concise'} wiki for this repository
2. Each page should focus on a specific aspect of the codebase (e.g., architecture, key features, setup)
3. The relevant_files should be actual files from the repository that would be used to generate that page
4. Return ONLY valid XML with the structure specified above, with no markdown code block delimiters'''
        
        return prompt
    
    def parse_wiki_structure_xml(self, xml_text: str) -> Optional[WikiStructure]:
        """Parse XML response to extract wiki structure"""
        try:
            # Clean up control characters
            xml_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', xml_text)
            
            # Remove markdown code blocks if present
            xml_text = re.sub(r'^```(?:xml)?\s*', '', xml_text, flags=re.IGNORECASE)
            xml_text = re.sub(r'```\s*$', '', xml_text, flags=re.IGNORECASE)
            
            # Extract wiki structure XML
            match = re.search(r'<wiki_structure>[\s\S]*?</wiki_structure>', xml_text, re.MULTILINE)
            if not match:
                logger.error('No valid XML found in response')
                return None
            
            xml_text = match.group(0)
            root = ET.fromstring(xml_text)
            
            # Extract basic structure
            title = root.findtext('title', '')
            description = root.findtext('description', '')
            
            # Parse pages
            pages = []
            pages_elem = root.find('pages')
            if pages_elem is not None:
                for page_elem in pages_elem.findall('page'):
                    page_id = page_elem.get('id', f'page-{len(pages) + 1}')
                    page_title = page_elem.findtext('title', '')
                    importance = page_elem.findtext('importance', 'medium')
                    
                    # Validate importance
                    if importance not in ['high', 'medium', 'low']:
                        importance = 'medium'
                    
                    # Get file paths
                    file_paths = []
                    relevant_files = page_elem.find('relevant_files')
                    if relevant_files is not None:
                        for file_path_elem in relevant_files.findall('file_path'):
                            if file_path_elem.text:
                                file_paths.append(file_path_elem.text)
                    
                    # Get related pages
                    related_pages = []
                    related_pages_elem = page_elem.find('related_pages')
                    if related_pages_elem is not None:
                        for related_elem in related_pages_elem.findall('related'):
                            if related_elem.text:
                                related_pages.append(related_elem.text)
                    
                    pages.append(WikiPage(
                        id=page_id,
                        title=page_title,
                        content='',
                        file_paths=file_paths,
                        importance=importance,  # type: ignore
                        related_pages=related_pages
                    ))
            
            # Parse sections if comprehensive view
            sections = []
            root_sections = []
            
            if self.is_comprehensive:
                sections_elem = root.find('sections')
                if sections_elem is not None:
                    section_ids = set()
                    for section_elem in sections_elem.findall('section'):
                        section_id = section_elem.get('id', f'section-{len(sections) + 1}')
                        section_title = section_elem.findtext('title', '')
                        
                        # Get page references
                        section_pages = []
                        pages_elem = section_elem.find('pages')
                        if pages_elem is not None:
                            for page_ref in pages_elem.findall('page_ref'):
                                if page_ref.text:
                                    section_pages.append(page_ref.text)
                        
                        # Get subsections
                        subsections = []
                        subsections_elem = section_elem.find('subsections')
                        if subsections_elem is not None:
                            for section_ref in subsections_elem.findall('section_ref'):
                                if section_ref.text:
                                    subsections.append(section_ref.text)
                        
                        sections.append(WikiSection(
                            id=section_id,
                            title=section_title,
                            pages=section_pages,
                            subsections=subsections if subsections else None
                        ))
                        section_ids.add(section_id)
                    
                    # Determine root sections (not referenced by other sections)
                    referenced_sections = set()
                    for section in sections:
                        if section.subsections:
                            referenced_sections.update(section.subsections)
                    
                    root_sections = [s.id for s in sections if s.id not in referenced_sections]
            
            return WikiStructure(
                id='wiki',
                title=title,
                description=description,
                pages=pages,
                sections=sections,
                root_sections=root_sections
            )
            
        except Exception as e:
            logger.error(f'Error parsing wiki structure XML: {e}')
            return None
    
    def to_dict(self, obj) -> Dict:
        """Convert dataclass to dictionary"""
        if hasattr(obj, '__dict__'):
            result = {}
            for key, value in obj.__dict__.items():
                if isinstance(value, list):
                    result[key] = [self.to_dict(item) if hasattr(item, '__dict__') else item for item in value]
                elif hasattr(value, '__dict__'):
                    result[key] = self.to_dict(value)
                else:
                    result[key] = value
            return result
        return obj
