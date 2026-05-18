// Image rendering functionality
// Detects image markers and places images ABOVE the tool panel
//
// Patch: preserve workspace-relative paths (including subdirectories) when
// constructing image URLs. The original _extractFilename() stripped all path
// components, causing images saved in subdirectories to return 404.

// Capture the workspace base directory sent by the server on WebSocket connect.
(function () {
    const _OrigWS = window.WebSocket;
    function PatchedWebSocket(url, protocols) {
        const ws = protocols !== undefined ? new _OrigWS(url, protocols) : new _OrigWS(url);
        ws.addEventListener('message', function (e) {
            try {
                const d = JSON.parse(e.data);
                if (d.type === 'base_directory_info' && d.base_directory) {
                    window._orchestralBaseDirectory = d.base_directory;
                }
            } catch (_) {}
        });
        return ws;
    }
    PatchedWebSocket.prototype = _OrigWS.prototype;
    Object.setPrototypeOf(PatchedWebSocket, _OrigWS);
    window.WebSocket = PatchedWebSocket;
})();

class ImageRenderer {
    constructor() {
        // Match text markers in format: [ORCHESTRAL_IMAGE:path/to/image.png]
        this.imageMarkerPattern = /\[ORCHESTRAL_IMAGE:(.*?)\]/g;
    }

    /**
     * Render images by detecting markers and placing images above panels
     * @param {HTMLElement} element - Container element to search for image markers
     */
    render(element) {
        // Find all elements with image markers
        const elementsWithMarkers = this._findElementsWithMarkers(element);

        if (elementsWithMarkers.length === 0) {
            return; // No markers found
        }

        // Process each element with markers
        elementsWithMarkers.forEach(({element: markerElement, imagePath}) => {
            // Find the closest .message ancestor (the panel container)
            const messageDiv = markerElement.closest('.message');

            if (messageDiv) {
                // Check if image already exists for this marker
                const existingImage = messageDiv.previousElementSibling;
                if (existingImage && existingImage.classList.contains('orchestral-image-container')) {
                    // Image already rendered, skip
                    return;
                }

                // Create and insert image above the message div
                const imageContainer = this._createImageElement(imagePath);
                messageDiv.parentNode.insertBefore(imageContainer, messageDiv);
            }

            // Hide the marker text from display
            this._hideMarkerText(markerElement);
        });
    }

    /**
     * Find all elements that contain image markers
     * @param {HTMLElement} element - Container to search
     * @returns {Array} Array of {element, imagePath} objects
     */
    _findElementsWithMarkers(element) {
        const results = [];
        const html = element.innerHTML;

        // Check if this element has markers
        this.imageMarkerPattern.lastIndex = 0;
        let match;

        while ((match = this.imageMarkerPattern.exec(html)) !== null) {
            results.push({
                element: element,
                imagePath: match[1]
            });
        }

        return results;
    }

    /**
     * Hide marker text from display
     * @param {HTMLElement} element - Element containing the marker
     */
    _hideMarkerText(element) {
        const walker = document.createTreeWalker(
            element,
            NodeFilter.SHOW_TEXT,
            null
        );

        const nodesToModify = [];
        while (walker.nextNode()) {
            const node = walker.currentNode;
            if (node.textContent.includes('[ORCHESTRAL_IMAGE:')) {
                nodesToModify.push(node);
            }
        }

        // Hide marker text by wrapping in hidden span
        nodesToModify.forEach(node => {
            const span = document.createElement('span');
            span.style.display = 'none';
            node.parentNode.insertBefore(span, node);
            span.appendChild(node);
        });
    }

    /**
     * Create an image element (DOM node, not HTML string)
     * @param {string} imagePath - Path to the image (as provided by the tool)
     * @returns {HTMLElement} Image container element
     */
    _createImageElement(imagePath) {
        // Preserve subdirectory structure relative to the workspace root.
        // The server endpoint /workspace-image/{file_path:path} already supports
        // subdirectory paths; we just need to pass them correctly.
        const relPath = this._getRelativePath(imagePath);

        // Encode each path segment individually to preserve slashes in the URL.
        const encodedPath = relPath.split('/').map(encodeURIComponent).join('/');
        const imageUrl = `/workspace-image/${encodedPath}`;

        // Create container div
        const container = document.createElement('div');
        container.className = 'orchestral-image-container';
        container.style.margin = '10px 0';
        container.style.textAlign = 'center';

        // Create image element
        const img = document.createElement('img');
        img.src = imageUrl;
        img.alt = relPath;
        img.className = 'orchestral-image';
        img.style.maxWidth = '100%';
        img.style.height = 'auto';
        img.style.borderRadius = '4px';
        img.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';

        // Create error message div
        const errorDiv = document.createElement('div');
        errorDiv.className = 'image-error';
        errorDiv.style.display = 'none';
        errorDiv.style.color = '#888';
        errorDiv.style.fontSize = '0.9em';
        errorDiv.style.padding = '10px';
        errorDiv.textContent = `Failed to load image: ${relPath}`;

        // Handle image load errors
        img.onerror = function() {
            img.style.display = 'none';
            errorDiv.style.display = 'block';
        };

        container.appendChild(img);
        container.appendChild(errorDiv);

        return container;
    }

    /**
     * Convert an absolute or relative image path to a workspace-relative path,
     * preserving any subdirectory structure.
     *
     * Examples (workspace = /home/user/project/workspace):
     *   /home/user/project/workspace/output/fit.png  → output/fit.png
     *   output/fit.png                               → output/fit.png
     *   fit.png                                      → fit.png
     *
     * @param {string} imagePath - Raw path from the tool
     * @returns {string} Workspace-relative path
     */
    _getRelativePath(imagePath) {
        const normalized = imagePath.replace(/\\/g, '/');

        // Already a relative path — use as-is.
        if (!normalized.startsWith('/')) {
            return normalized;
        }

        // Absolute path: strip workspace base directory if known.
        const baseDir = window._orchestralBaseDirectory;
        if (baseDir) {
            const normalizedBase = baseDir.replace(/\\/g, '/').replace(/\/$/, '');
            if (normalized.startsWith(normalizedBase + '/')) {
                return normalized.slice(normalizedBase.length + 1);
            }
        }

        // Fallback: return just the filename (original behaviour).
        const parts = normalized.split('/');
        return parts[parts.length - 1];
    }

    /**
     * Check if element contains image markers
     * @param {HTMLElement} element - Element to check
     * @returns {boolean}
     */
    hasImageMarkers(element) {
        this.imageMarkerPattern.lastIndex = 0;
        return this.imageMarkerPattern.test(element.innerHTML);
    }
}

// Export for use in main app
window.ImageRenderer = ImageRenderer;
