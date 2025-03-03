// frontend_utils.js - Utility functions for Supabase authentication and library management

// Function to link a Supabase user with the Django backend
async function linkSupabaseUser(supabaseUserId, email, username = null) {
  try {
    const response = await fetch('/api/auth/link-supabase-user', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        supabase_user_id: supabaseUserId,
        email: email,
        username: username || email,
      }),
    });
    
    return await response.json();
  } catch (error) {
    console.error('Error linking Supabase user:', error);
    throw error;
  }
}

// Function to get Django user details from a Supabase user ID
async function getDjangoUser(supabaseUserId) {
  try {
    const response = await fetch(`/api/auth/get-django-user?supabase_user_id=${supabaseUserId}`);
    return await response.json();
  } catch (error) {
    console.error('Error getting Django user:', error);
    throw error;
  }
}

// Function to save a case to the library
async function saveCaseToLibrary(supabaseUserId, caseId) {
  try {
    const response = await fetch('/api/library/save', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        supabase_user_id: supabaseUserId,
        case_id: caseId,
      }),
    });
    
    return await response.json();
  } catch (error) {
    console.error('Error saving case to library:', error);
    throw error;
  }
}

// Function to remove a case from the library
async function removeCaseFromLibrary(supabaseUserId, caseId) {
  try {
    const response = await fetch(`/api/library/remove/${caseId}?supabase_user_id=${supabaseUserId}`, {
      method: 'DELETE',
    });
    
    return await response.json();
  } catch (error) {
    console.error('Error removing case from library:', error);
    throw error;
  }
}

// Function to check if a case is in the library
async function isCaseInLibrary(supabaseUserId, caseId) {
  try {
    const response = await fetch(`/api/library/check/${caseId}?supabase_user_id=${supabaseUserId}`);
    const data = await response.json();
    return data.is_in_library;
  } catch (error) {
    console.error('Error checking if case is in library:', error);
    return false;
  }
}

// Function to get all cases in the user's library
async function getUserLibrary(supabaseUserId) {
  try {
    const response = await fetch(`/api/library?supabase_user_id=${supabaseUserId}`);
    const data = await response.json();
    return data.cases || [];
  } catch (error) {
    console.error('Error getting user library:', error);
    return [];
  }
}

// Example: How to use these functions in a React component

/* 
// Example React component for a Save to Library button
function SaveToLibraryButton({ caseId }) {
  const [isSaved, setIsSaved] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const { user } = useSupabaseAuth(); // Assuming you have a custom hook for Supabase auth
  
  useEffect(() => {
    async function checkSavedStatus() {
      if (user) {
        setIsLoading(true);
        try {
          const saved = await isCaseInLibrary(user.id, caseId);
          setIsSaved(saved);
        } catch (error) {
          console.error('Error checking saved status:', error);
        } finally {
          setIsLoading(false);
        }
      }
    }
    
    checkSavedStatus();
  }, [user, caseId]);
  
  const handleToggleSave = async () => {
    if (!user) {
      // Handle not logged in case
      return;
    }
    
    setIsLoading(true);
    try {
      if (isSaved) {
        await removeCaseFromLibrary(user.id, caseId);
        setIsSaved(false);
      } else {
        await saveCaseToLibrary(user.id, caseId);
        setIsSaved(true);
      }
    } catch (error) {
      console.error('Error toggling save status:', error);
    } finally {
      setIsLoading(false);
    }
  };
  
  if (isLoading) {
    return <button disabled>Loading...</button>;
  }
  
  return (
    <button onClick={handleToggleSave}>
      {isSaved ? 'Remove from Library' : 'Save to Library'}
    </button>
  );
}
*/

// Export all functions for use in other files
export {
  linkSupabaseUser,
  getDjangoUser,
  saveCaseToLibrary,
  removeCaseFromLibrary,
  isCaseInLibrary,
  getUserLibrary
}; 