import { IExecuteFunctions } from 'n8n-core';
import {
    INodeExecutionData,
    INodeType,
    INodeTypeDescription,
    NodeOperationError,
} from 'n8n-workflow';
import FormData from 'form-data';

export class DoclingExtractor implements INodeType {
    description: INodeTypeDescription = {
        displayName: 'Docling Extractor',
        name: 'doclingExtractor',
        group: ['transform'],
        version: 1,
        description: 'Process documents with enhanced extraction for RAG workflows',
        defaults: {
            name: 'Docling Extractor',
            color: '#125580',
        },
        inputs: ['main'],
        outputs: ['main'],
        properties: [
            {
                displayName: 'Operation',
                name: 'operation',
                type: 'options',
                options: [
                    {
                        name: 'Standard Extraction',
                        value: 'extract',
                        description: 'Extract content from document',
                    },
                    {
                        name: 'Supabase Ready',
                        value: 'extractSupabase',
                        description: 'Extract and format for Supabase integration',
                    },
                ],
                default: 'extractSupabase',
                required: true,
            },
            {
                displayName: 'Docling API URL',
                name: 'apiUrl',
                type: 'string',
                default: 'http://localhost:8000',
                required: true,
                description: 'URL of the Docling extractor API',
            },
            {
                displayName: 'Document',
                name: 'binaryPropertyName',
                type: 'string',
                default: 'data',
                required: true,
                displayOptions: {
                    show: {
                        operation: ['extract', 'extractSupabase'],
                    },
                },
                description: 'Name of the binary property that contains the document file',
            },
            {
                displayName: 'File ID',
                name: 'fileId',
                type: 'string',
                default: '',
                required: false,
                displayOptions: {
                    show: {
                        operation: ['extract', 'extractSupabase'],
                    },
                },
                description: 'Optional identifier for the document (will be generated if not provided)',
            },
            {
                displayName: 'File Title',
                name: 'fileTitle',
                type: 'string',
                default: '',
                required: false,
                displayOptions: {
                    show: {
                        operation: ['extract', 'extractSupabase'],
                    },
                },
                description: 'Optional title for the document (will use filename if not provided)',
            },
            {
                displayName: 'Advanced Options',
                name: 'options',
                type: 'collection',
                placeholder: 'Add Option',
                default: {},
                displayOptions: {
                    show: {
                        operation: ['extract', 'extractSupabase'],
                    },
                },
                options: [
                    {
                        displayName: 'Extract Technical Terms',
                        name: 'extractTechnicalTerms',
                        type: 'boolean',
                        default: true,
                        description: 'Whether to extract technical terms from the document',
                    },
                    {
                        displayName: 'Extract Procedures',
                        name: 'extractProcedures',
                        type: 'boolean',
                        default: true,
                        description: 'Whether to extract procedures and parameters from the document',
                    },
                    {
                        displayName: 'Extract Relationships',
                        name: 'extractRelationships',
                        type: 'boolean',
                        default: true,
                        description: 'Whether to extract relationships between concepts',
                    },
                    {
                        displayName: 'Process Images',
                        name: 'processImages',
                        type: 'boolean',
                        default: true,
                        description: 'Whether to process and extract images from the document',
                    },
                    {
                        displayName: 'Process Tables',
                        name: 'processTables',
                        type: 'boolean',
                        default: true,
                        description: 'Whether to process and extract tables from the document',
                    },
                    {
                        displayName: 'Chunk Size',
                        name: 'chunkSize',
                        type: 'number',
                        default: 500,
                        description: 'Size of text chunks for extraction',
                    },
                    {
                        displayName: 'Chunk Overlap',
                        name: 'chunkOverlap',
                        type: 'number',
                        default: 100,
                        description: 'Overlap between chunks',
                    },
                ],
            },
        ],
    };

    async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
        const items = this.getInputData();
        const returnItems: INodeExecutionData[] = [];

        // For each item
        for (let itemIndex = 0; itemIndex < items.length; itemIndex++) {
            try {
                // Get parameters
                const operation = this.getNodeParameter('operation', itemIndex) as string;
                const apiUrl = this.getNodeParameter('apiUrl', itemIndex) as string;
                const binaryPropertyName = this.getNodeParameter('binaryPropertyName', itemIndex) as string;
                const fileId = this.getNodeParameter('fileId', itemIndex, '') as string;
                const fileTitle = this.getNodeParameter('fileTitle', itemIndex, '') as string;
                const options = this.getNodeParameter('options', itemIndex, {}) as {
                    extractTechnicalTerms?: boolean;
                    extractProcedures?: boolean;
                    extractRelationships?: boolean;
                    processImages?: boolean;
                    processTables?: boolean;
                    chunkSize?: number;
                    chunkOverlap?: number;
                };

                // Check if binary data exists
                if (items[itemIndex].binary === undefined) {
                    throw new NodeOperationError(
                        this.getNode(),
                        'No binary data exists on item!',
                        { itemIndex },
                    );
                }

                const binaryData = items[itemIndex].binary![binaryPropertyName];
                if (binaryData === undefined) {
                    throw new NodeOperationError(
                        this.getNode(),
                        `No binary data property '${binaryPropertyName}' exists on item!`,
                        { itemIndex },
                    );
                }

                // Create FormData for file upload
                const formData = new FormData();

                // Add file
                const buffer = Buffer.from(binaryData.data, 'base64');
                formData.append('file', buffer, {
                    filename: binaryData.fileName || 'document.pdf',
                    contentType: binaryData.mimeType,
                });

                // Add parameters
                if (fileId) {
                    formData.append('file_id', fileId);
                }
                if (fileTitle) {
                    formData.append('file_title', fileTitle);
                }
                if (options.extractTechnicalTerms !== undefined) {
                    formData.append('extract_technical_terms', options.extractTechnicalTerms.toString());
                }
                if (options.extractProcedures !== undefined) {
                    formData.append('extract_procedures', options.extractProcedures.toString());
                }
                if (options.extractRelationships !== undefined) {
                    formData.append('extract_relationships', options.extractRelationships.toString());
                }
                if (options.processImages !== undefined) {
                    formData.append('process_images', options.processImages.toString());
                }
                if (options.processTables !== undefined) {
                    formData.append('process_tables', options.processTables.toString());
                }
                if (options.chunkSize !== undefined) {
                    formData.append('chunk_size', options.chunkSize.toString());
                }
                if (options.chunkOverlap !== undefined) {
                    formData.append('chunk_overlap', options.chunkOverlap.toString());
                }

                // Determine endpoint URL based on operation
                let endpoint = '';
                if (operation === 'extract') {
                    endpoint = '/api/extract';
                } else if (operation === 'extractSupabase') {
                    endpoint = '/api/extract-supabase-ready';
                }

                // Make request to API
                const response = await this.helpers.httpRequestWithAuthentication.call(
                    this,
                    'httpBasicAuth',
                    {
                        method: 'POST',
                        url: apiUrl + endpoint,
                        body: formData,
                        headers: {
                            ...formData.getHeaders(),
                        },
                        json: true,
                    },
                );

                returnItems.push({
                    json: response,
                    binary: {},
                });
            } catch (error) {
                if (this.continueOnFail()) {
                    returnItems.push({
                        json: {
                            error: error.message,
                        },
                        binary: {},
                    });
                    continue;
                }
                throw error;
            }
        }

        return [returnItems];
    }
}
