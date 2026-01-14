#!/usr/bin/env python3
"""
CLI tool for DeepWiki repository processing.

Usage:
    Generate embeddings for a GitHub repository:
        python api/cli.py generate https://github.com/owner/repo
    
    Generate embeddings for a local repository:
        python api/cli.py generate /path/to/local/repo
    
    Generate embeddings for a private repository:
        python api/cli.py generate https://github.com/owner/repo --access-token TOKEN
    
    Generate embeddings for a GitLab repository:
        python api/cli.py generate https://gitlab.com/owner/repo --repo-type gitlab
    
    Generate wiki with custom output:
        python api/cli.py generate https://github.com/owner/repo --output ./wiki_output --model-provider google
"""
# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

import click
import logging
import sys
import os
from urllib.parse import urlparse
from api.data_pipeline import DatabaseManager
from api.logging_config import setup_logging
from api.rag import RAG
from api.repo_wiki_gen import WikiGenerator, RepoInfo

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


@click.group()
def cli():
    """DeepWiki CLI - Repository processing and embedding generation."""
    pass

# .venv/bin/python -m api.cli generate /nfs/site/disks/ssm_lwang85_002/AI/repo-wiki/AdalFlow --repo-type "github" --output /nfs/site/disks/ssm_lwang85_002/AI/repo-wiki/AdalFlow/.deepwiki --model-provider "dashscope" --model "qwen3-coder-plus"

@cli.command()
@click.argument('repo_path')
@click.option(
    '--repo-type',
    type=click.Choice(['github', 'gitlab', 'bitbucket'], case_sensitive=False),
    default='github',
    help='Type of repository (default: github)'
)
@click.option(
    '--access-token',
    help='Access token for private repositories'
)
@click.option(
    '--model-provider',
    default='google',
    help='Model provider for wiki generation (google, openai, openrouter, ollama, etc.)'
)
@click.option(
    '--model',
    default='qwen3-coder-plus',
    help='Model name for wiki generation (default: qwen3-coder-plus)'
)
@click.option(
    '--output',
    type=click.Path(),
    help='Output directory for generated wiki markdown files'
)
def generate(repo_path, repo_type, access_token, model_provider, model, output):
    """
    Generate embeddings database and wiki for a repository.
    
    REPO_PATH: Repository URL or local path to process
    """
    try:
        logger.info(f"Starting generation for repository: {repo_path}")
        print(f"======== embedder type: {os.environ.get('DEEPWIKI_EMBEDDER_TYPE')} ========")
        
        # Parse repository information
        repo_url = repo_path
        if repo_path.startswith('http://') or repo_path.startswith('https://'):
            parsed = urlparse(repo_path)
            path_parts = parsed.path.strip('/').split('/')
            if len(path_parts) >= 2:
                owner = path_parts[-2]
                repo = path_parts[-1].replace('.git', '')
            else:
                raise ValueError("Invalid repository URL format")
            local_path = None
        else:
            # Local path
            owner = os.path.basename(repo_path)
            repo = owner
            local_path = repo_path
            repo_url = None
        
        # Create RepoInfo object
        repo_info = RepoInfo(
            owner=owner,
            repo=repo,
            type=repo_type,
            token=access_token,
            local_path=local_path,
            repo_url=repo_url
        )
        
        logger.info(f"Repository: {owner}/{repo} (type: {repo_type})")
        
        # Step 1: Create output directory
        if output:
            output_dir = output
        else:
            output_dir = f"./.deepwiki"
        
        os.makedirs(output_dir, exist_ok=True)
        click.echo(f"Output directory: {output_dir}")
        
        # Step 2: Create RAG instance
        click.echo("Creating RAG instance...")
        request_rag = RAG(provider=model_provider, model=model)
        
        # Step 3: Prepare retriever (this creates/loads the .pkl database)
        click.echo("Preparing retriever and embeddings...")
        request_rag.prepare_retriever(
            repo_url_or_path=repo_path,
            type=repo_type,
            access_token=access_token,
            excluded_dirs=None,
            excluded_files=None,
            included_dirs=None,
            included_files=None
        )
        logger.info(f"Retriever prepared for {repo_path}")
        click.echo(click.style("✓ Retriever prepared successfully", fg='green'))
        
        # Step 4: Create WikiGenerator
        click.echo("Creating wiki generator...")
        wiki_generator = WikiGenerator(
            repo_info=repo_info,
            language='en',
            provider=model_provider,
            model=model,
            is_comprehensive=True
        )
        
        # Step 5: Generate wiki structure
        click.echo("Generating wiki structure...")
        
        # Get file tree and README (simplified - in production you'd fetch these properly)
        file_tree = "Repository file tree will be analyzed by RAG"
        readme = "README content will be analyzed by RAG"
        
        structure_prompt = wiki_generator.create_wiki_structure_prompt(file_tree, readme)
        
        # Query RAG for context (retrieve relevant documents)
        logger.info("Querying RAG for wiki structure")
        retrieved_docs = request_rag.call(structure_prompt, language='en')
        
        # Format context from retrieved documents
        context_text = ""
        if retrieved_docs and retrieved_docs[0].documents:
            documents = retrieved_docs[0].documents
            logger.info(f"Retrieved {len(documents)} documents for structure")
            click.echo(f"  Retrieved {len(documents)} documents:")        
            # Group documents by file path
            docs_by_file = {}
            for doc in documents:
                file_path = doc.meta_data.get('file_path', 'unknown')
                if file_path not in docs_by_file:
                    docs_by_file[file_path] = []
                docs_by_file[file_path].append(doc)

            # Format context text with file path grouping
            context_parts = []
            for file_path, docs in docs_by_file.items():
                # Add file header with metadata
                header = f"## File Path: {file_path}\n\n"
                # Add document content
                content = "\n\n".join([doc.text for doc in docs])

                context_parts.append(f"{header}{content}")

            # Join all parts with clear separation
            context_text = "\n\n" + "-" * 10 + "\n\n".join(context_parts)
        # Generate structure using the LLM with context
        from api.config import get_model_config
        model_config = get_model_config(model_provider, model)
        
        # Create prompt with context
        full_prompt = f"""<context>
{context_text}
</context>

<task>
{structure_prompt}
</task>"""
        
        # Call the generator
        from adalflow.core.types import ModelType
        generator_client = model_config["model_client"]()
        api_kwargs = model_config["model_kwargs"].copy()
        api_kwargs["messages"] = [{"role": "user", "content": full_prompt}]
        
        logger.info("Generating wiki structure with LLM")
        structure_response = generator_client.call(api_kwargs=api_kwargs, model_type=ModelType.LLM)
        
        # Extract response text
        if hasattr(structure_response, 'choices') and len(structure_response.choices) > 0:
            structure_xml = structure_response.choices[0].message.content
        elif hasattr(structure_response, 'content'):
            structure_xml = structure_response.content
        else:
            structure_xml = str(structure_response)
        
        logger.info(f"Received wiki structure XML (length: {len(structure_xml)})")
        
        # # Write structure XML to file for debugging/inspection
        # structure_xml_file = os.path.join(output_dir, "wiki_structure.xml")
        # os.makedirs(os.path.dirname(structure_xml_file), exist_ok=True)
        # with open(structure_xml_file, 'w', encoding='utf-8') as f:
        #     f.write(structure_xml)
        # logger.info(f"Written wiki structure XML to: {structure_xml_file}")
        
        # Parse wiki structure
        wiki_structure = wiki_generator.parse_wiki_structure_xml(structure_xml)
        
        if not wiki_structure:
            raise ValueError("Failed to parse wiki structure XML")
        
        click.echo(click.style(f"✓ Wiki structure created with {len(wiki_structure.pages)} pages", fg='green'))
        logger.info(f"Wiki structure: {wiki_structure.title}")
        
        # Step 6: Generate content for each page
        click.echo(f"\nGenerating content for {len(wiki_structure.pages)} pages...")
        
        for idx, page in enumerate(wiki_structure.pages, 1):
            click.echo(f"\n[{idx}/{len(wiki_structure.pages)}] Generating: {page.title}")
            logger.info(f"Generating page: {page.id} - {page.title}")
            
            # Create page content prompt
            content_prompt = wiki_generator.create_page_content_prompt(page)
            
            # Query RAG for context
            logger.info(f"Querying RAG for page content: {page.title}")
            retrieved_docs = request_rag.call(content_prompt, language='en')
            
            # Format context from retrieved documents
            context_text = ""
            if retrieved_docs and retrieved_docs[0].documents:
                documents = retrieved_docs[0].documents
                logger.info(f"Retrieved {len(documents)} documents for page")
                context_parts = []
                for doc in documents[:15]:  # Limit to top 15 documents for page content
                    file_path = doc.meta_data.get('file_path', 'unknown')
                    context_parts.append(f"File: {file_path}\n{doc.text}")
                context_text = "\n\n---\n\n".join(context_parts)
            
            # Generate content using the LLM with context
            full_prompt = f"""<context>
{context_text}
</context>

<task>
{content_prompt}
</task>"""
            
            # Call the generator
            api_kwargs = model_config["model_kwargs"].copy()
            api_kwargs["messages"] = [{"role": "user", "content": full_prompt}]
            
            content_response = generator_client.call(api_kwargs=api_kwargs, model_type=ModelType.LLM)
            
            # Extract response text
            if hasattr(content_response, 'data'):
                page_content = content_response.data
            elif hasattr(content_response, 'choices') and len(content_response.choices) > 0:
                page_content = content_response.choices[0].message.content
            elif hasattr(content_response, 'content'):
                page_content = content_response.content
            else:
                page_content = str(content_response)
            
            if not page_content:
                logger.warning(f"Failed to generate content for page: {page.title}")
                click.echo(click.style(f"  ⚠ Warning: No content generated", fg='yellow'))
                continue
            
            # Clean up markdown delimiters if present
            page_content = page_content.replace('```markdown', '').replace('```', '')
            
            # Write to markdown file
            # Sanitize filename
            safe_filename = "".join(c for c in page.title if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_filename = safe_filename.replace(' ', '_')
            markdown_file = os.path.join(output_dir, f"{safe_filename}.md")
            
            with open(markdown_file, 'w', encoding='utf-8') as f:
                f.write(page_content)
            
            click.echo(click.style(f"  ✓ Written to: {markdown_file}", fg='green'))
            logger.info(f"Written page to: {markdown_file}")
        
        # Step 7: Create index file
        index_file = os.path.join(output_dir, "README.md")
        with open(index_file, 'w', encoding='utf-8') as f:
            f.write(f"# {wiki_structure.title}\n\n")
            f.write(f"{wiki_structure.description}\n\n")
            f.write("## Pages\n\n")
            for page in wiki_structure.pages:
                safe_filename = "".join(c for c in page.title if c.isalnum() or c in (' ', '-', '_')).strip()
                safe_filename = safe_filename.replace(' ', '_')
                f.write(f"- [{page.title}](./{safe_filename}.md)\n")
        
        click.echo(click.style(f"\n✓ Wiki generation completed successfully!", fg='green', bold=True))
        click.echo(f"✓ Generated {len(wiki_structure.pages)} wiki pages")
        click.echo(f"✓ Output directory: {output_dir}")
        
    except Exception as e:
        logger.error(f"Error during generation: {e}", exc_info=True)
        click.echo(click.style(f"✗ Error: {e}", fg='red'), err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
